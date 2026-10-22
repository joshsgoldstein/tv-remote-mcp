"""Experimental LG webOS SSAP adapter. No implicit pairing in status/discovery."""

import json
import ssl
from contextlib import contextmanager
from time import monotonic
from urllib.parse import urlsplit

from websocket import WebSocketException, create_connection

from .network_tv import NetworkIntegration

PERMISSIONS = [
    "LAUNCH",
    "CONTROL_AUDIO",
    "CONTROL_INPUT_MEDIA_PLAYBACK",
    "CONTROL_INPUT_TV",
    "CONTROL_INPUT_TEXT",
    "CONTROL_MOUSE_AND_KEYBOARD",
    "CONTROL_POWER",
    "READ_INSTALLED_APPS",
    "READ_APP_STATUS",
]


class LGConnection:
    def __init__(self, tv):
        self.tv = tv
        self.socket = None

    def open_socket(self, url, timeout=5):
        # LG TVs use local self-signed certificates. Do not use system HTTP proxies.
        parsed = urlsplit(url)
        if (
            parsed.hostname != self.tv.host
            or parsed.scheme not in ("ws", "wss")
            or parsed.port not in (3000, 3001)
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Invalid LG input socket address")
        return create_connection(
            url,
            timeout=timeout,
            suppress_origin=True,
            sslopt={"cert_reqs": ssl.CERT_NONE},
            http_no_proxy=[self.tv.host],
        )

    def connect(self):
        scheme = "wss" if self.tv.port == 3001 else "ws"
        self.socket = self.open_socket(f"{scheme}://{self.tv.host}:{self.tv.port}/")

    def exchange(self, message, expected, timeout=5):
        self.guard()
        self.socket.send(json.dumps(message))
        deadline = monotonic() + timeout
        for _ in range(64):
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            self.socket.settimeout(remaining)
            raw = self.socket.recv()
            if len(raw) > 1024 * 1024:
                raise RuntimeError("LG response exceeded the size limit")
            response = json.loads(raw)
            if response.get("id") != message["id"]:
                continue
            if (
                response.get("type") == "error"
                or response.get("payload", {}).get("returnValue") is False
            ):
                raise RuntimeError(
                    "LG rejected the request. Check TV authorization and model support."
                )
            if response.get("type") == expected:
                return response.get("payload", {})
        raise RuntimeError("LG response timed out")

    def hello(self):
        return self.exchange(
            {
                "type": "hello",
                "id": "hello",
                "payload": {
                    "sdkVersion": "1.0",
                    "deviceModel": "Home Control",
                    "appId": "home-control",
                },
            },
            "hello",
        )

    def register(self, key, pairing=False):
        payload = {
            "forcePairing": False,
            "pairingType": "PROMPT",
            "manifest": {"manifestVersion": 1, "appVersion": "1.0", "permissions": PERMISSIONS},
        }
        if key:
            payload["client-key"] = key
        if not key and not pairing:
            raise ValueError("Pair this LG TV first")
        result = self.exchange(
            {"type": "register", "id": "register", "payload": payload},
            "registered",
            timeout=25 if pairing else 5,
        )
        if not result.get("client-key"):
            raise RuntimeError("LG did not return a pairing key")
        return result["client-key"]

    def request(self, uri, payload=None):
        return self.exchange(
            {"type": "request", "id": "request", "uri": "ssap://" + uri, "payload": payload or {}},
            "response",
        )

    def button(self, key):
        location = self.request("com.webos.service.networkinput/getPointerInputSocket")[
            "socketPath"
        ]
        with self.open_socket(location) as pointer:
            self.guard()
            pointer.send(f"type:button\nname:{key}\n\n")

    def close(self):
        if self.socket:
            self.socket.close()


class LGIntegration(NetworkIntegration):
    id = "lg_webos"
    name = "LG webOS (experimental)"
    manufacturer = "LG"
    pairing_message = (
        "Choose Allow on the LG TV when you select Pair television. This can take up to 25 seconds."
    )
    keys = {
        key: key.upper()
        for key in [
            "up",
            "down",
            "left",
            "right",
            "home",
            "back",
            "menu",
            "exit",
            "info",
            "mute",
            "play",
            "pause",
            "stop",
            "rewind",
            "red",
            "green",
            "yellow",
            "blue",
            *map(str, range(10)),
        ]
    }
    keys.update(
        {
            "enter": "ENTER",
            "volume_up": "VOLUMEUP",
            "volume_down": "VOLUMEDOWN",
            "channel_up": "CHANNELUP",
            "channel_down": "CHANNELDOWN",
            "forward": "FASTFORWARD",
        }
    )

    @contextmanager
    def connection(self, tv):
        client = LGConnection(tv)
        client.guard = lambda: self.record(tv.id, command=True)
        try:
            client.connect()
            client.info = client.hello()
            # Newer webOS firmware expects this read before registration.
            try:
                client.request("system/getSystemInfo")
            except RuntimeError:
                pass  # Older TVs can reject this optional information endpoint.
            self.identity(tv, client.info.get("deviceUUID"))
            yield client
        except (OSError, WebSocketException, KeyError, json.JSONDecodeError):
            raise RuntimeError(
                "LG connection failed. Check the TV address, port, and authorization."
            ) from None
        finally:
            client.close()

    def execute(self, device_id, action, parameters):
        data = self.validate(action, parameters)
        with self.gate(device_id) as tv:
            if action == "power" and data.power == "on":
                return self.wake(tv)
            saved = self.store.credential(self.id, device_id)
            if action != "pair" and not saved.get("client_key"):
                raise ValueError("Pair this LG TV first")
            with self.connection(tv) as client:
                hello = client.info
                key = client.register(saved.get("client_key"), pairing=action == "pair")
                self.record(device_id, command=True)
                if action == "pair":
                    self.store.save_credential(
                        self.id, device_id, {"client_key": key}, hello["deviceUUID"]
                    )
                    return {"status": "connected", "token_saved": True}
                if action == "key":
                    for _ in range(data.times):
                        self.record(device_id, command=True)
                        client.button(self.keys[data.key])
                elif action == "power":
                    client.request("system/turnOff")
                elif action == "text":
                    client.request(
                        "com.webos.service.ime/insertText", {"text": data.text, "replace": 0}
                    )
                elif action == "apps":
                    response = client.request("com.webos.applicationManager/listApps")
                    return {
                        "apps": [
                            {"app_id": item["id"], "name": item.get("title", item["id"])}
                            for item in response.get("apps", [])
                            if item.get("id")
                        ]
                    }
                elif action == "launch":
                    client.request("system.launcher/launch", {"id": data.app_id})
            return {"status": "command_sent"}
