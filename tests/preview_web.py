"""Synthetic data for browser QA only. Never connects to a television."""

import tempfile
from pathlib import Path

import uvicorn

from tv_remote_mcp.config import TV, NetworkTV, Settings, Store
from tv_remote_mcp.control import Controller
from tv_remote_mcp.home import Home
from tv_remote_mcp.integrations.lg import LGIntegration
from tv_remote_mcp.integrations.samsung import SamsungIntegration
from tv_remote_mcp.integrations.sony import SonyIntegration
from tv_remote_mcp.web import create_app


class PreviewController(Controller):
    art_mode = "off"

    def status(self, tv_id):
        return {
            **self.store.public(self.store.tv(tv_id)),
            "reachable": True,
            "identity_matches": True,
            "power": "on",
        }

    def discover(self, save=False):
        return {"found": self.list_tvs(), "configured": self.list_tvs(), "saved": save}

    def pair(self, tv_id):
        self.store.token_path(self.store.tv(tv_id)).write_text("fixture-only")
        return {"status": "connected", "token_saved": True}

    def key(self, tv_id, key, times=1):
        return {"status": "command_sent", "key": key, "times": times}

    def power(self, tv_id, action):
        return {"status": "wake_packet_sent" if action == "on" else "command_sent"}

    def text(self, tv_id, text):
        return {"status": "command_sent"}

    def apps(self, tv_id):
        return {"apps": [{"name": "Example player", "appId": "example.player"}]}

    def launch(self, tv_id, app_id, app_type="DEEP_LINK"):
        return {"status": "command_sent"}

    def art_status(self, tv_id):
        return {"art_mode": self.art_mode}

    def set_art_mode(self, tv_id, enabled):
        self.art_mode = "on" if enabled else "off"
        return {"art_mode": self.art_mode, "requested": enabled}

    def list_art(self, tv_id):
        return {"artworks": [{"name": "Sample artwork", "content_id": "sample"}]}

    def select_art(self, tv_id, content_id):
        return {"status": "command_sent"}


class PreviewNetwork:
    def status(self, device_id):
        return {"reachable": True, "power": None}

    def discover(self, save=False):
        return {"found": [item.model_dump() for item in self.devices()], "saved": save}

    def execute(self, device_id, action, parameters):
        self.validate(action, parameters)
        with self.gate(device_id):
            if action == "pair":
                self.store.save_credential(
                    self.id, device_id, {"fixture": "demo-only"}, "demo-identity"
                )
                return {"status": "connected", "token_saved": True}
            if action == "apps":
                return {"apps": [{"app_id": "demo.player", "name": "Demo player"}]}
            return {"status": "command_sent"}


class PreviewLG(PreviewNetwork, LGIntegration):
    pass


class PreviewSony(PreviewNetwork, SonyIntegration):
    pass


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "config.json")
        store.save(
            Settings(
                tvs=[
                    TV(
                        id="frame",
                        name="Living room",
                        host="192.168.1.10",
                        frame=True,
                        mac="02:00:00:00:00:01",
                        model="The Frame",
                    ),
                    TV(id="samsung", name="Bedroom", host="192.168.1.11", model="Samsung Smart TV"),
                ],
                devices=[
                    NetworkTV(
                        integration="lg_webos",
                        id="lg",
                        name="Office",
                        host="192.168.1.12",
                        model="LG webOS demo",
                    ),
                    NetworkTV(
                        integration="sony_bravia",
                        id="sony",
                        name="Den",
                        host="192.168.1.13",
                        port=80,
                        model="Sony BRAVIA demo",
                    ),
                ],
            )
        )
        store.token_path(store.tv("frame")).write_text("fixture-only")
        store.save_credential("lg_webos", "lg", {"fixture": "demo-only"}, "demo-lg")
        control = PreviewController(store)
        home = Home(store, [SamsungIntegration(control), PreviewLG(store), PreviewSony(store)])
        uvicorn.run(create_app(control, home=home), host="127.0.0.1", port=8766)
