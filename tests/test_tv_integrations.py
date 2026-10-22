"""Synthetic protocol fixtures only. No home inventory or hardware commands."""

import json
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient

from tv_remote_mcp.config import TV, NetworkTV, Settings, Store
from tv_remote_mcp.control import Controller
from tv_remote_mcp.home import create_home
from tv_remote_mcp.integrations import lg, sony, ssdp
from tv_remote_mcp.web import create_app


@pytest.fixture(params=["lg_webos", "sony_bravia"])
def vendor(request, tmp_path):
    store = Store(tmp_path / "config.json")
    kind = request.param
    tv = NetworkTV(
        integration=kind,
        id="sample",
        name="Sample TV",
        host="192.168.1.20",
        port=3001 if kind == "lg_webos" else 80,
    )
    store.save(
        Settings(tvs=[TV(id="frame", name="Sample Frame", host="192.168.1.10")], devices=[tv])
    )
    return store, kind, create_home(Controller(store)).integration(kind)


def fake_client(monkeypatch, kind):
    client = MagicMock()
    if kind == "lg_webos":
        client.hello.return_value = {"deviceUUID": "fixture-lg-id"}
        client.register.return_value = "fixture-private-client-key"
        monkeypatch.setattr(lg, "LGConnection", MagicMock(return_value=client))
    else:
        client.identity.return_value = "fixture-sony-id"
        client.rpc.return_value = [{}, [{"name": "Home", "value": "AAAAAA=="}]]
        monkeypatch.setattr(sony, "SonyClient", MagicMock(return_value=client))
    return client


def pair(adapter, kind):
    return adapter.execute(
        "sample", "pair", {"psk": "fixture-private-psk"} if kind == "sony_bravia" else {}
    )


def test_pair_keys_apps_and_secret_storage(vendor, monkeypatch):
    store, kind, adapter = vendor
    client = fake_client(monkeypatch, kind)
    assert pair(adapter, kind)["token_saved"]
    credential = store.credential_path(kind, "sample")
    assert credential.stat().st_mode & 0o777 == 0o600
    assert store.tv("frame").name == "Sample Frame"
    assert "fixture-private" not in json.dumps(adapter.devices()[0].model_dump())
    assert "fixture-private" not in store.path.read_text()
    assert (
        adapter.execute("sample", "key", {"key": "KEY_HOME", "times": 2})["status"]
        == "command_sent"
    )
    assert client.button.call_count == 2
    if kind == "lg_webos":
        client.request.return_value = {"apps": [{"id": "sample.player", "title": "Sample player"}]}
    else:
        client.rpc.return_value = [[{"uri": "sample:player", "title": "Sample player"}]]
    apps = adapter.execute("sample", "apps", {})["apps"]
    assert apps[0]["name"] == "Sample player"
    assert apps[0]["app_id"]


def test_persistent_switches_block_direct_pair_wake_and_commands(vendor, monkeypatch):
    store, kind, adapter = vendor
    client = fake_client(monkeypatch, kind)
    adapter.set_enabled("sample", False)
    for action, params in [("pair", {}), ("power", {"power": "on"}), ("key", {"key": "home"})]:
        with pytest.raises(ValueError, match="kill switch"):
            adapter.execute("sample", action, params)
    client.connect.assert_not_called()
    client.identity.assert_not_called()
    fresh = create_home(Controller(Store(store.path)))
    with pytest.raises(ValueError, match="kill switch"):
        fresh.execute(f"{kind}:sample", "pair", {})
    adapter.set_enabled("sample", True)
    store.set_enabled(False)
    with pytest.raises(ValueError, match="kill switch"):
        pair(adapter, kind)


def test_no_auth_network_calls_for_status_inventory_or_discovery(vendor, monkeypatch):
    store, kind, adapter = vendor
    client = fake_client(monkeypatch, kind)
    tcp = MagicMock()
    monkeypatch.setattr("tv_remote_mcp.integrations.network_tv.socket.create_connection", tcp)
    monkeypatch.setattr("tv_remote_mcp.integrations.network_tv.discover", lambda *args: [])
    assert adapter.status("sample")["power"] is None
    adapter.devices()
    assert adapter.discover(True)["found"] == []
    client.connect.assert_not_called()
    client.register.assert_not_called()
    client.identity.assert_not_called()


def test_identity_change_and_disabled_during_pair_never_persist_secret(vendor, monkeypatch):
    store, kind, adapter = vendor
    client = fake_client(monkeypatch, kind)
    if kind == "lg_webos":
        client.register.side_effect = lambda *a, **kw: (
            store.set_enabled(False),
            "new-fixture-key",
        )[1]
    else:
        client.identity.side_effect = lambda: (store.set_enabled(False), "fixture-sony-id")[1]
    with pytest.raises(ValueError, match="kill switch"):
        pair(adapter, kind)
    assert store.credential(kind, "sample") == {}
    store.set_enabled(True)
    client.register.side_effect = None
    client.identity.side_effect = None
    pair(adapter, kind)
    if kind == "lg_webos":
        client.hello.return_value = {"deviceUUID": "different-fixture-device"}
    else:
        client.identity.return_value = "different-fixture-device"
    client.button.reset_mock()
    with pytest.raises(ValueError, match="identity"):
        adapter.execute("sample", "key", {"key": "home"})
    client.button.assert_not_called()


def test_merge_preserves_ids_switches_credentials_and_samsung(vendor):
    store, kind, adapter = vendor
    adapter.set_enabled("sample", False)
    store.save_credential(kind, "sample", {"fixture": "private"}, "fixture-identity")
    tv = store.network_tv(kind, "sample").model_copy(
        update={"id": "new", "name": "New discovery name", "discovery_id": "fixture-udn"}
    )
    store.merge_network([tv])
    saved = store.network_tv(kind, "sample")
    assert saved.name == "Sample TV" and not saved.enabled
    assert saved.device_id == "fixture-identity"
    assert store.credential(kind, "sample") == {"fixture": "private"}
    assert store.tv("frame").id == "frame"
    tv.host = "192.168.1.21"
    store.merge_network([tv])
    assert store.network_tv(kind, "sample").host == tv.host


def test_web_add_validation_and_sony_psk_is_not_echoed(tmp_path, monkeypatch):
    store = Store(tmp_path / "config.json")
    client = TestClient(create_app(Controller(store)), headers={"X-TV-Remote": "1"})
    # Host guard intentionally rejects an unexpected host.
    assert client.post("/api/devices", json={}).status_code == 403
    client = TestClient(
        create_app(Controller(store), allowed_hosts={"testserver"}), headers={"X-TV-Remote": "1"}
    )
    for host in ["127.0.0.1", "example.com", "8.8.8.8"]:
        assert (
            client.post(
                "/api/devices", json={"integration": "sony_bravia", "host": host, "name": "Test"}
            ).status_code
            == 400
        )
    assert (
        client.post(
            "/api/devices",
            json={"integration": "lg_webos", "host": "192.168.1.20", "name": "Test", "port": 80},
        ).status_code
        == 400
    )
    assert not store.path.exists()
    assert (
        client.post(
            "/api/devices",
            json={"integration": "sony_bravia", "host": "192.168.1.20", "name": "Test"},
        ).status_code
        == 200
    )
    fake = fake_client(monkeypatch, "sony_bravia")
    fake.identity.side_effect = RuntimeError("Sony authentication failed")
    response = client.post(
        "/api/devices/sony_bravia:sony/action", json={"action": "pair", "psk": "fixture-secret"}
    )
    assert response.status_code == 503
    assert "fixture-secret" not in response.text
    assert "fixture-secret" not in client.get("/api/state").text
    assert store.credential("sony_bravia", "sony") == {}


def test_lg_wire_format_and_pointer_host_boundary(monkeypatch):
    tv = NetworkTV(integration="lg_webos", id="lg", name="Test", host="192.168.1.20")
    sock = MagicMock()
    sock.recv.side_effect = [
        json.dumps({"type": "response", "id": "register", "payload": {"pairingType": "PROMPT"}}),
        json.dumps(
            {"type": "registered", "id": "register", "payload": {"client-key": "fixture-key"}}
        ),
    ]
    connect = MagicMock(return_value=sock)
    monkeypatch.setattr(lg, "create_connection", connect)
    client = lg.LGConnection(tv)
    client.guard = MagicMock()
    client.connect()
    assert client.register(None, pairing=True) == "fixture-key"
    request = json.loads(sock.send.call_args.args[0])
    assert request["type"] == "register"
    assert request["payload"]["pairingType"] == "PROMPT"
    with pytest.raises(ValueError, match="Invalid LG"):
        client.open_socket("ws://192.168.1.99:3000/input")
    assert connect.call_count == 1


def test_sony_wire_format_redacts_auth_failure(monkeypatch):
    tv = NetworkTV(integration="sony_bravia", id="sony", name="Test", host="192.168.1.20", port=80)
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"result":[{"status":"active"}]}'
    opener = MagicMock()
    opener.open.return_value = response
    monkeypatch.setattr(sony, "build_opener", lambda *a: opener)
    client = sony.SonyClient(tv, "fixture-secret")
    client.guard = MagicMock()
    assert client.rpc("system", "getPowerStatus")[0]["status"] == "active"
    req = opener.open.call_args.args[0]
    assert req.full_url == "http://192.168.1.20:80/sony/system"
    assert json.loads(req.data)["method"] == "getPowerStatus"
    client.button("AAAAAA==")
    req = opener.open.call_args.args[0]
    assert b"<IRCCCode>AAAAAA==</IRCCCode>" in req.data
    opener.open.side_effect = OSError("fixture-secret")
    with pytest.raises(RuntimeError) as caught:
        client.rpc("system", "getPowerStatus")
    assert "fixture-secret" not in str(caught.value)


def test_ssdp_rejects_unrelated_hosts_redirects_and_entities(monkeypatch):
    opener = MagicMock()
    monkeypatch.setattr(ssdp, "build_opener", lambda *a: opener)
    for url in [
        "http://127.0.0.1/d.xml",
        "http://192.168.1.99/d.xml",
        "https://192.168.1.20/d.xml",
        "http://192.168.1.20:9999/d.xml",
    ]:
        assert ssdp.description(url, "192.168.1.20", "192.168.1.0/24") is None
    opener.open.assert_not_called()
    response = opener.open.return_value.__enter__.return_value
    response.read.return_value = b'<!DOCTYPE test [<!ENTITY x "bad">]><root />'
    assert ssdp.description("http://192.168.1.20/d.xml", "192.168.1.20", "192.168.1.0/24") is None
    response.read.return_value = b"<root><device><manufacturer>LG Electronics</manufacturer><deviceType>urn:schemas-upnp-org:device:MediaRenderer:1</deviceType><friendlyName>Sample LG</friendlyName><UDN>uuid:fixture</UDN></device></root>"
    assert (
        ssdp.description("http://192.168.1.20/d.xml", "192.168.1.20", "192.168.1.0/24").integration
        == "lg_webos"
    )


def test_advertised_schemas_match_vendor_limits(vendor):
    store, kind, adapter = vendor
    assert adapter.action_schemas["power"]["properties"]["power"]["enum"] == ["on", "off"]
    assert adapter.action_schemas["launch"]["properties"]["app_id"]["maxLength"] == 2048
    if kind == "sony_bravia":
        assert "text" not in adapter.action_schemas
        assert adapter.action_schemas["pair"]["properties"]["psk"]["writeOnly"]
    else:
        assert "source" not in adapter.keys
    for action, params in [
        ("power", {"power": "toggle"}),
        ("key", {"key": "factory"}),
        ("launch", {"app_id": ""}),
    ]:
        with pytest.raises(ValueError):
            adapter.execute("sample", action, params)


def test_protocol_guard_stops_before_network_send(monkeypatch):
    tv = NetworkTV(integration="lg_webos", id="lg", name="Test", host="192.168.1.20")
    client = lg.LGConnection(tv)
    client.socket = MagicMock()
    client.guard = MagicMock(side_effect=ValueError("kill switch"))
    with pytest.raises(ValueError, match="kill switch"):
        client.register("fixture-key")
    client.socket.send.assert_not_called()
    tv = NetworkTV(integration="sony_bravia", id="sony", name="Test", host="192.168.1.20", port=80)
    opener = MagicMock()
    monkeypatch.setattr(sony, "build_opener", lambda *a: opener)
    client = sony.SonyClient(tv, "fixture-key")
    client.guard = MagicMock(side_effect=ValueError("kill switch"))
    with pytest.raises(ValueError, match="kill switch"):
        client.rpc("system", "setPowerStatus", [{"status": False}])
    opener.open.assert_not_called()
