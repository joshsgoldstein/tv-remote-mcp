"""Exercise the integration boundary with a non-TV device and no hardware."""

import json
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from tv_remote_mcp.config import TV, Settings, Store
from tv_remote_mcp.control import Controller
from tv_remote_mcp.home import Home, create_home
from tv_remote_mcp.integrations import Device
from tv_remote_mcp.web import create_app


class SampleLight:
    id = "sample_light"
    name = "Test-only light"
    action_schemas = {
        "brightness": {
            "type": "object",
            "properties": {"level": {"type": "integer", "minimum": 0, "maximum": 100}},
            "required": ["level"],
            "additionalProperties": False,
        }
    }

    def __init__(self, store):
        self.path = store.path.parent / "sample-light.json"
        self.calls = []

    def devices(self):
        enabled = json.loads(self.path.read_text()) if self.path.exists() else True
        return [
            Device(
                id="living_room",
                name="Sample light",
                category="light",
                manufacturer="Test fixture",
                enabled=enabled,
                paired=True,
                capabilities=["brightness"],
                actions=["brightness"],
            )
        ]

    def discover(self, save=False):
        return {"found": [], "saved": save}

    def status(self, device_id):
        return {"reachable": True, "brightness": 50}

    def execute(self, device_id, action, parameters):
        if (
            set(parameters) != {"level"}
            or type(parameters["level"]) is not int
            or not 0 <= parameters["level"] <= 100
        ):
            raise ValueError("Brightness must be an integer from 0 to 100")
        self.calls.append((device_id, action, parameters))
        return {"status": "command_sent"}

    def set_enabled(self, device_id, enabled):
        self.path.write_text(json.dumps(enabled))
        return {"enabled": enabled}


@pytest.fixture
def home(tmp_path):
    store = Store(tmp_path / "config.json")
    light = SampleLight(store)
    return Home(store, [light]), light


def test_non_tv_routes_without_samsung_assumptions(home):
    hub, light = home
    device = hub.devices()[0]
    assert device["id"] == "sample_light:living_room"
    assert device["category"] == "light"
    assert "art" not in device["capabilities"]
    assert hub.status(device["id"])["brightness"] == 50
    assert hub.execute(device["id"], "brightness", {"level": 60})["status"] == "command_sent"
    assert light.calls == [("living_room", "brightness", {"level": 60})]
    assert hub.catalog()[0]["action_schemas"]["brightness"]["required"] == ["level"]


def test_planned_and_unsupported_operations_never_dispatch(home):
    hub, light = home
    for op in [
        lambda: hub.execute("sample_light:living_room", "art_mode", {}),
        lambda: hub.discover("lg_webos", True),
        lambda: hub.status("sony_bravia:tv"),
        lambda: hub.execute("living_room", "brightness", {"level": 2}),
    ]:
        with pytest.raises(ValueError):
            op()
    assert light.calls == []


def test_shared_kill_switch_applies_to_non_tv_and_survives_new_hub(home):
    hub, light = home
    hub.set_enabled("sample_light:living_room", False)
    fresh = Home(Store(hub.store.path), [SampleLight(hub.store)])
    with pytest.raises(ValueError, match="kill switch"):
        fresh.execute("sample_light:living_room", "brightness", {"level": 10})
    hub.set_enabled("sample_light:living_room", True)
    hub.store.set_enabled(False)
    with pytest.raises(ValueError, match="kill switch"):
        hub.execute("sample_light:living_room", "brightness", {"level": 10})
    assert hub.status("sample_light:living_room")["reachable"]
    assert light.calls == []


def test_generic_web_routes_use_the_same_gate(home):
    hub, light = home
    client = TestClient(create_app(home=hub, allowed_hosts={"testserver"}))
    state = client.get("/api/state").json()
    assert state["devices"][0]["category"] == "light"
    assert any(i["id"] == "sony_bravia" and i["status"] == "planned" for i in state["integrations"])
    headers = {"X-TV-Remote": "1"}
    route = "/api/devices/sample_light:living_room"
    assert (
        client.post(
            route + "/action", json={"action": "brightness", "level": 5}, headers=headers
        ).status_code
        == 200
    )
    assert (
        client.post(
            route + "/action", json={"action": "brightness", "level": 101}, headers=headers
        ).status_code
        == 400
    )
    assert (
        client.post(route + "/controls", json={"enabled": False}, headers=headers).status_code
        == 200
    )
    assert (
        client.post(
            route + "/action", json={"action": "brightness", "level": 6}, headers=headers
        ).status_code
        == 400
    )
    assert len(light.calls) == 1


def test_samsung_adapter_preserves_existing_switches_and_validates_parameters(
    tmp_path, monkeypatch
):
    store = Store(tmp_path / "config.json")
    store.save(Settings(tvs=[TV(id="frame", name="Frame", host="192.168.1.10", frame=True)]))
    controller = Controller(store)
    pair = MagicMock(return_value={"status": "connected"})
    monkeypatch.setattr(controller, "pair", pair)
    hub = create_home(controller)
    assert hub.devices()[0]["id"] == "samsung:frame"
    assert "art" in hub.devices()[0]["capabilities"]
    hub.execute("samsung:frame", "pair", {})
    pair.assert_called_once_with("frame")
    hub.set_enabled("samsung:frame", False)
    assert not store.tv("frame").enabled
    with pytest.raises(ValueError, match="kill switch"):
        hub.execute("samsung:frame", "pair", {})
    store.set_enabled(True, "frame")
    with pytest.raises(ValueError, match="Missing required"):
        hub.execute("samsung:frame", "power", {})
    with pytest.raises(ValueError, match="Unsupported parameters"):
        hub.execute("samsung:frame", "pair", {"power": "on"})
