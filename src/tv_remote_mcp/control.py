from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Literal

from samsungtvws import SamsungTVWS
from samsungtvws.exceptions import ConnectionFailure, ResponseError, UnauthorizedError
from websocket import WebSocketException

from .config import Store
from .discovery import device_info, discover, wake

# The upstream library logs pairing tokens at INFO. Never expose them in MCP logs.
logging.getLogger("samsungtvws").setLevel(logging.ERROR)

KEYS = {
    "up": "KEY_UP",
    "down": "KEY_DOWN",
    "left": "KEY_LEFT",
    "right": "KEY_RIGHT",
    "enter": "KEY_ENTER",
    "back": "KEY_RETURN",
    "home": "KEY_HOME",
    "menu": "KEY_MENU",
    "exit": "KEY_EXIT",
    "source": "KEY_SOURCE",
    "guide": "KEY_GUIDE",
    "info": "KEY_INFO",
    "volume_up": "KEY_VOLUP",
    "volume_down": "KEY_VOLDOWN",
    "mute": "KEY_MUTE",
    "channel_up": "KEY_CHUP",
    "channel_down": "KEY_CHDOWN",
    "play": "KEY_PLAY",
    "pause": "KEY_PAUSE",
    "stop": "KEY_STOP",
    "rewind": "KEY_REWIND",
    "forward": "KEY_FF",
    "hdmi": "KEY_HDMI",
    "red": "KEY_RED",
    "green": "KEY_GREEN",
    "yellow": "KEY_YELLOW",
    "blue": "KEY_BLUE",
    **{str(i): f"KEY_{i}" for i in range(10)},
}


class Controller:
    def __init__(self, store: Store | None = None):
        self.store = store or Store()

    def list_tvs(self) -> list[dict]:
        return [self.store.public(tv) for tv in self.store.load().tvs]

    def discover(self, save: bool = False) -> dict:
        found = discover(self.store.load().subnet)
        configured = self.store.merge(found) if save else self.store.load().tvs
        return {
            "found": [tv.model_dump() for tv in found],
            "saved": save,
            "configured": [self.store.public(tv) for tv in configured],
            "note": "Sleeping TVs may not respond. Turn on missing TVs and run again.",
        }

    def status(self, tv_id: str) -> dict:
        tv = self.store.tv(tv_id)
        result = self.store.public(tv)
        try:
            try:
                data = device_info(tv.host)
            except (OSError, ValueError):
                data = device_info(tv.host, port=tv.port)
            device = data["device"]
            actual_id = device.get("id")
            if tv.device_id and actual_id != tv.device_id:
                return {
                    **result,
                    "reachable": True,
                    "identity_matches": False,
                    "power": "unknown",
                    "note": "IP belongs to a different TV. Rediscover before controlling it.",
                }
            return {
                **result,
                "reachable": True,
                "identity_matches": True,
                "power": device.get("PowerState", "unknown"),
                "note": "PowerState does not distinguish TV playback from Art Mode.",
            }
        except (OSError, ValueError):
            return {
                **result,
                "reachable": False,
                "power": "unknown",
                "note": "TV may be asleep, offline, or at a new DHCP address. This does not prove it is powered off.",
            }

    @contextmanager
    def connection(self, tv_id: str, *, art: bool = False, pairing: bool = False):
        tv = self.store.require_enabled(tv_id)
        if art and not tv.frame:
            raise ValueError(f"{tv.name} is not configured as a Frame TV")
        token = self.store.token_path(tv)
        if not pairing and tv.port == 8002 and (not token.exists() or not token.stat().st_size):
            raise ValueError(
                f"{tv.name} needs pairing. Run pair_tv and select Allow on its screen."
            )
        with self.store.lock(tv.id):
            tv = self.store.require_enabled(tv_id)
            # Prevent a stale DHCP lease from sending commands to the wrong TV.
            try:
                info = device_info(tv.host)
            except (OSError, ValueError):
                info = device_info(tv.host, port=tv.port)
            if tv.device_id and info["device"].get("id") != tv.device_id:
                raise ValueError("TV identity changed at this IP. Run discover_tvs(save=True).")
            # Precreate the token with private permissions before the library writes it.
            token.touch(mode=0o600, exist_ok=True)
            token.chmod(0o600)
            remote = SamsungTVWS(
                tv.host,
                port=tv.port,
                token_file=str(token),
                name="Samsung TV Remote MCP",
                timeout=25 if pairing else 8,
                key_press_delay=0.35,
            )
            client = remote.art() if art else remote
            try:
                yield client
            except UnauthorizedError:
                raise RuntimeError(
                    "TV denied access. Run pair_tv while someone selects Allow for Samsung TV Remote MCP on the TV."
                ) from None
            except (ConnectionFailure, WebSocketException, OSError):
                raise RuntimeError(
                    "TV connection failed or timed out. Check it is on and reachable; if pairing, select Allow on its screen. No successful action was confirmed."
                ) from None
            except ResponseError:
                raise RuntimeError(
                    "TV rejected this operation; support varies by model and firmware."
                ) from None
            finally:
                client.close()
                if client is not remote:
                    remote.close()
                if token.exists():
                    token.chmod(0o600)

    def pair(self, tv_id: str) -> dict:
        with self.connection(tv_id, pairing=True) as tv:
            tv.open()
        return {
            "tv": tv_id,
            "status": "connected",
            "token_saved": self.store.public(self.store.tv(tv_id))["token_saved"],
        }

    def key(self, tv_id: str, key: str, times: int = 1) -> dict:
        code = KEYS.get(key.lower(), key.upper())
        if code not in KEYS.values():
            raise ValueError("Unsupported key. Use list_remote_keys; power has a separate tool.")
        if not 1 <= times <= 20:
            raise ValueError("times must be between 1 and 20")
        with self.connection(tv_id) as tv:
            tv.send_key(code, times=times)
        return {"tv": tv_id, "status": "command_sent", "key": code, "times": times}

    def power(self, tv_id: str, action: Literal["on", "off", "toggle"]) -> dict:
        tv = self.store.tv(tv_id)
        if action == "on":
            with self.store.lock(tv.id):
                tv = self.store.require_enabled(tv_id)
                return wake(tv, self.store.load().subnet)
        if action not in ("off", "toggle"):
            raise ValueError("Power action must be on, off, or toggle")
        with self.connection(tv_id) as remote:
            if action == "off" and tv.frame:
                remote.hold_key("KEY_POWER", 3)
            else:
                remote.send_key("KEY_POWEROFF" if action == "off" else "KEY_POWER")
        return {
            "tv": tv_id,
            "status": "command_sent",
            "action": action,
            "note": "Check status separately. A Frame power toggle may switch TV/Art Mode.",
        }

    def text(self, tv_id: str, text: str) -> dict:
        if not 1 <= len(text) <= 500:
            raise ValueError("Text must contain 1–500 characters")
        with self.connection(tv_id) as tv:
            tv.send_text(text)
        return {"tv": tv_id, "status": "command_sent"}

    def apps(self, tv_id: str) -> dict:
        with self.connection(tv_id) as tv:
            apps = tv.app_list()
        return {
            "tv": tv_id,
            "apps": apps,
            "note": "App enumeration is not supported by every firmware.",
        }

    def launch(self, tv_id: str, app_id: str, app_type: str = "DEEP_LINK") -> dict:
        if not app_id or len(app_id) > 128 or app_type not in ("DEEP_LINK", "NATIVE_LAUNCH"):
            raise ValueError("Provide a valid app_id and DEEP_LINK or NATIVE_LAUNCH")
        with self.connection(tv_id) as tv:
            tv.run_app(app_id, app_type=app_type)
        return {"tv": tv_id, "status": "command_sent", "app_id": app_id}

    def art_status(self, tv_id: str) -> dict:
        with self.connection(tv_id, art=True) as art:
            mode = art.get_artmode()
        return {"tv": tv_id, "art_mode": mode}

    def set_art_mode(self, tv_id: str, enabled: bool) -> dict:
        with self.connection(tv_id, art=True) as art:
            art.set_artmode(enabled)
            mode = art.get_artmode()
        return {"tv": tv_id, "art_mode": mode, "requested": enabled}

    def list_art(self, tv_id: str) -> dict:
        with self.connection(tv_id, art=True) as art:
            items = art.available()
        return {"tv": tv_id, "artworks": items}

    def select_art(self, tv_id: str, content_id: str) -> dict:
        if not content_id or len(content_id) > 128:
            raise ValueError("Provide a content_id from list_artwork")
        with self.connection(tv_id, art=True) as art:
            art.select_image(content_id, show=True)
        return {"tv": tv_id, "status": "command_sent", "content_id": content_id}

    def upload_art(self, tv_id: str, filename: str, matte: str = "none") -> dict:
        root = (self.store.path.parent / "artwork").resolve()
        path = (root / filename).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Image must exist inside the server's config/artwork directory")
        if path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("Image must be smaller than 20 MiB")
        data = path.read_bytes()
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            kind = "png"
        elif data.startswith(b"\xff\xd8\xff"):
            kind = "jpg"
        else:
            raise ValueError("Only PNG and JPEG images are supported")
        with self.connection(tv_id, art=True) as art:
            content_id = art.upload(data, file_type=kind, matte=matte, portrait_matte=matte)
        return {
            "tv": tv_id,
            "content_id": content_id,
            "status": "uploaded",
            "note": "Use select_artwork to display it.",
        }
