"""Synthetic data for browser QA only. Never connects to a television."""

import tempfile
from pathlib import Path

import uvicorn

from tv_remote_mcp.config import TV, Settings, Store
from tv_remote_mcp.control import Controller
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
                ]
            )
        )
        store.token_path(store.tv("frame")).write_text("fixture-only")
        uvicorn.run(create_app(PreviewController(store)), host="127.0.0.1", port=8766)
