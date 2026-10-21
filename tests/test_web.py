from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from tv_remote_mcp.config import TV, Settings, Store
from tv_remote_mcp.control import Controller
from tv_remote_mcp.web import create_app


@pytest.fixture
def setup(tmp_path):
    store = Store(tmp_path / "config.json")
    store.save(Settings(tvs=[TV(id="frame", name="Living room", host="192.168.1.10", frame=True)]))
    control = Controller(store)
    app = create_app(control, allowed_hosts={"testserver"})
    return control, TestClient(app)


def post(client, path, data):
    return client.post(path, json=data, headers={"X-TV-Remote": "1"})


def test_web_shell_and_assets_are_packaged(setup):
    _, client = setup
    response = client.get("/")
    assert response.status_code == 200
    assert "Remote control" in response.text
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_inventory_does_not_include_token_contents(setup):
    control, client = setup
    control.store.token_path(control.store.tv("frame")).write_text("private-pairing-token")
    response = client.get("/api/state")
    assert response.status_code == 200
    assert response.json()["tvs"][0]["token_saved"] is True
    assert "private-pairing-token" not in response.text


def test_only_explicit_pair_action_can_pair(setup, monkeypatch):
    control, client = setup
    pair = MagicMock(return_value={"status": "connected", "token_saved": True})
    monkeypatch.setattr(control, "pair", pair)
    response = post(client, "/api/tvs/frame/action", {"action": "pair"})
    assert response.status_code == 200
    pair.assert_called_once_with("frame")


def test_normal_command_for_unpaired_tv_fails_without_connection(setup):
    _, client = setup
    response = post(client, "/api/tvs/frame/action", {"action": "key", "key": "home"})
    assert response.status_code == 400
    assert "needs pairing" in response.json()["error"]


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "evil.example", "X-TV-Remote": "1"},
        {"Origin": "https://evil.example", "X-TV-Remote": "1"},
        {"Sec-Fetch-Site": "cross-site", "X-TV-Remote": "1"},
        {},
    ],
)
def test_browser_requests_cannot_be_forged_cross_origin(setup, monkeypatch, headers):
    control, client = setup
    pair = MagicMock()
    monkeypatch.setattr(control, "pair", pair)
    assert (
        client.post("/api/tvs/frame/action", json={"action": "pair"}, headers=headers).status_code
        == 403
    )
    pair.assert_not_called()


def test_lan_access_token_required_and_not_in_shell(setup):
    control, _ = setup
    secret = "test-only-long-server-access-token"
    client = TestClient(create_app(control, allowed_hosts={"testserver"}, access_token=secret))
    assert secret not in client.get("/").text
    assert client.get("/api/state").status_code == 401
    assert client.get("/api/state", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert (
        client.get("/api/state", headers={"Authorization": f"Bearer {secret}"}).status_code == 200
    )


def test_saving_subnet_preserves_devices_and_rejects_large_scan(setup):
    control, client = setup
    assert post(client, "/api/network", {"subnet": "10.0.0.0/24"}).status_code == 200
    assert control.store.load().subnet == "10.0.0.0/24"
    assert control.store.tv("frame").name == "Living room"
    assert post(client, "/api/network", {"subnet": "10.0.0.0/8"}).status_code == 400
    assert control.store.load().subnet == "10.0.0.0/24"


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "execute", "command": "anything"},
        {"action": "key", "key": "home", "times": 21},
        {"action": "art_mode", "enabled": "false"},
        {"action": "key", "key": "KEY_FACTORY"},
        {"action": "power", "power": "anything"},
    ],
)
def test_invalid_actions_do_not_reach_tv(setup, payload):
    _, client = setup
    assert post(client, "/api/tvs/frame/action", payload).status_code == 400


def test_pair_timeout_is_an_error_not_success(setup, monkeypatch):
    control, client = setup
    monkeypatch.setattr(control, "pair", MagicMock(side_effect=RuntimeError("Pairing timed out")))
    response = post(client, "/api/tvs/frame/action", {"action": "pair"})
    assert response.status_code == 503
    assert response.json() == {"error": "Pairing timed out"}


def test_power_and_art_commands_dispatch_to_shared_controller(setup, monkeypatch):
    control, client = setup
    power = MagicMock(return_value={"status": "command_sent"})
    art = MagicMock(return_value={"art_mode": "on"})
    monkeypatch.setattr(control, "power", power)
    monkeypatch.setattr(control, "set_art_mode", art)
    assert (
        post(client, "/api/tvs/frame/action", {"action": "power", "power": "off"}).status_code
        == 200
    )
    assert (
        post(client, "/api/tvs/frame/action", {"action": "art_mode", "enabled": True}).status_code
        == 200
    )
    power.assert_called_once_with("frame", "off")
    art.assert_called_once_with("frame", True)


def test_json_size_and_content_type_are_bounded(setup):
    _, client = setup
    assert post(client, "/api/discover", {"padding": "x" * 17000}).status_code == 400
    assert (
        client.post("/api/discover", content="{}", headers={"X-TV-Remote": "1"}).status_code == 415
    )


def test_web_kill_switch_persists_and_blocks_mcp_controller(setup):
    control, client = setup
    assert post(client, "/api/tvs/frame/controls", {"enabled": False}).status_code == 200
    other = Controller(Store(control.store.path))
    with pytest.raises(ValueError, match="kill switch"):
        other.pair("frame")
    assert not client.get("/api/state").json()["tvs"][0]["enabled"]
    assert post(client, "/api/tvs/frame/controls", {"enabled": True}).status_code == 200
    assert post(client, "/api/controls", {"enabled": False}).status_code == 200
    assert not client.get("/api/state").json()["controls_enabled"]
    assert (
        post(client, "/api/tvs/frame/action", {"action": "power", "power": "on"}).status_code == 400
    )
    assert post(client, "/api/controls", {"enabled": "true"}).status_code == 400
    assert post(client, "/api/tvs/missing/controls", {"enabled": False}).status_code == 400


def test_private_reverse_proxy_accepts_only_configured_external_origin(setup):
    control, _ = setup
    client = TestClient(
        create_app(control, allowed_hosts={"testserver"}, external_origin="https://home.example")
    )
    assert (
        client.post(
            "/api/controls",
            json={"enabled": False},
            headers={"X-TV-Remote": "1", "Origin": "https://home.example"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/controls",
            json={"enabled": True},
            headers={
                "X-TV-Remote": "1",
                "Origin": "https://other.example",
                "X-Forwarded-Proto": "https",
            },
        ).status_code
        == 403
    )
