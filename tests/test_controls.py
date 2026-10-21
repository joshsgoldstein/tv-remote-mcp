from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from samsungtvws.exceptions import UnauthorizedError

from tv_remote_mcp import control, discovery
from tv_remote_mcp.config import TV, Settings, Store
from tv_remote_mcp.control import Controller


@pytest.fixture
def setup(tmp_path):
    store = Store(tmp_path / "config.json")
    frame = TV(
        id="frame",
        name="The Frame",
        host="192.168.1.10",
        frame=True,
        mac="02:00:00:00:00:01",
        device_id="uuid:frame",
    )
    second = TV(id="samsung", name="Bedroom", host="192.168.1.11", device_id="uuid:second")
    store.save(Settings(tvs=[frame, second]))
    return store, Controller(store)


def test_rediscovery_keeps_names_tokens_and_offline_tv(setup):
    store, _ = setup
    token = store.token_path(store.tv("frame"))
    token.write_text("secret")
    moved = store.tv("frame").model_copy(update={"host": "192.168.1.20", "name": "Factory name"})
    store.merge([moved])
    assert store.tv("frame").host == "192.168.1.20"
    assert store.tv("frame").name == "The Frame"
    assert store.tv("samsung").name == "Bedroom"
    assert token.read_text() == "secret"


def test_reused_ip_does_not_inherit_token(setup):
    store, _ = setup
    new = TV(id="frame", name="New TV", host="192.168.1.10", device_id="uuid:different")
    store.merge([new])
    assert store.tv("frame").device_id == "uuid:frame"
    assert store.tv("frame-2").device_id == "uuid:different"


@pytest.mark.parametrize("subnet", ["0.0.0.0/0", "192.168.0.0/16", "8.8.8.0/24", "127.0.0.0/24"])
def test_scan_bounds(subnet):
    with pytest.raises(ValidationError):
        Settings(subnet=subnet)


def test_unknown_tv_never_falls_back(setup):
    _, controller = setup
    with pytest.raises(ValueError, match="Unknown TV"):
        controller.key("missing", "home")


def test_unpaired_read_and_commands_do_not_create_pairing_prompt(setup, monkeypatch):
    _, controller = setup
    constructor = MagicMock()
    monkeypatch.setattr(control, "SamsungTVWS", constructor)
    for operation in (
        lambda: controller.key("frame", "home"),
        lambda: controller.art_status("frame"),
    ):
        with pytest.raises(ValueError, match="needs pairing"):
            operation()
    constructor.assert_not_called()


def test_device_identity_checked_before_command(setup, monkeypatch):
    store, controller = setup
    store.token_path(store.tv("frame")).write_text("secret")
    monkeypatch.setattr(control, "device_info", lambda *a, **kw: {"device": {"id": "uuid:other"}})
    constructor = MagicMock()
    monkeypatch.setattr(control, "SamsungTVWS", constructor)
    with pytest.raises(ValueError, match="identity changed"):
        controller.key("frame", "home")
    constructor.assert_not_called()


def test_timeout_does_not_report_power_off(setup, monkeypatch):
    _, controller = setup
    monkeypatch.setattr(control, "device_info", MagicMock(side_effect=TimeoutError))
    assert controller.status("frame")["power"] == "unknown"
    assert controller.status("frame")["reachable"] is False


def test_pair_denied_is_actionable_and_closes(setup, monkeypatch):
    store, controller = setup
    monkeypatch.setattr(control, "device_info", lambda *a, **kw: {"device": {"id": "uuid:frame"}})
    remote = MagicMock()
    remote.open.side_effect = UnauthorizedError("sensitive response")
    monkeypatch.setattr(control, "SamsungTVWS", MagicMock(return_value=remote))
    with pytest.raises(RuntimeError, match="selects Allow") as error:
        controller.pair("frame")
    assert "sensitive" not in str(error.value)
    remote.close.assert_called_once()
    assert store.token_path(store.tv("frame")).stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("key,times", [("KEY_FACTORY", 1), ("home", 21), ("home", 0)])
def test_invalid_keys_and_repeat_bounds_before_connect(setup, monkeypatch, key, times):
    _, controller = setup
    connection = MagicMock()
    monkeypatch.setattr(controller, "connection", connection)
    with pytest.raises(ValueError):
        controller.key("frame", key, times)
    connection.assert_not_called()


def fake_connection(monkeypatch, controller):
    client = MagicMock()

    @contextmanager
    def connect(*args, **kwargs):
        yield client

    monkeypatch.setattr(controller, "connection", connect)
    return client


def test_frame_off_long_press_and_regular_off_discrete_key(setup, monkeypatch):
    _, controller = setup
    client = fake_connection(monkeypatch, controller)
    controller.power("frame", "off")
    client.hold_key.assert_called_once_with("KEY_POWER", 3)
    controller.power("samsung", "off")
    client.send_key.assert_called_once_with("KEY_POWEROFF")


def test_art_mode_reports_readback_instead_of_assuming_success(setup, monkeypatch):
    _, controller = setup
    client = fake_connection(monkeypatch, controller)
    client.get_artmode.return_value = "off"
    result = controller.set_art_mode("frame", True)
    assert result == {"tv": "frame", "art_mode": "off", "requested": True}


def test_art_rejected_for_non_frame(setup):
    _, controller = setup
    with pytest.raises(ValueError, match="not configured as a Frame"):
        controller.art_status("samsung")


def test_art_upload_cannot_escape_artwork_directory(setup, tmp_path):
    _, controller = setup
    (tmp_path / "private.png").write_bytes(b"\x89PNG\r\n\x1a\nsecret")
    with pytest.raises(ValueError, match="inside"):
        controller.upload_art("frame", "../private.png")


def test_wake_packet_is_for_selected_tv_and_home_subnet(setup, monkeypatch):
    store, _ = setup
    sock = MagicMock()
    monkeypatch.setattr(discovery.socket, "socket", MagicMock(return_value=sock))
    result = discovery.wake(store.tv("frame"), "192.168.1.0/24")
    packet, destination = sock.__enter__.return_value.sendto.call_args.args
    assert packet == b"\xff" * 6 + bytes.fromhex("020000000001") * 16
    assert destination == ("192.168.1.255", 9)
    assert result["status"] == "wake_packet_sent"


def test_discovery_falls_back_to_tls_and_decodes_name(monkeypatch):
    def info(host, timeout, port):
        if port == 8001:
            raise OSError("closed")
        return {
            "device": {
                "type": "Samsung SmartTV",
                "name": "50&quot; Frame",
                "FrameTVSupport": "true",
                "TokenAuthSupport": "true",
            }
        }

    monkeypatch.setattr(discovery, "device_info", info)
    found = discovery.probe("192.168.1.10")
    assert found.name == '50" Frame'
    assert found.port == 8002
    assert found.frame


def test_kill_switch_blocks_connections_and_wake_across_controllers(setup, monkeypatch):
    store, controller = setup
    network = MagicMock()
    monkeypatch.setattr(control, "SamsungTVWS", network)
    monkeypatch.setattr(control, "wake", network)
    monkeypatch.setattr(control, "device_info", network)
    store.set_enabled(False, "frame")
    another = Controller(Store(store.path))
    for operation in (
        lambda: another.key("frame", "home"),
        lambda: another.pair("frame"),
        lambda: another.power("frame", "on"),
        lambda: another.power("frame", "off"),
        lambda: another.set_art_mode("frame", True),
        lambda: another.apps("frame"),
    ):
        with pytest.raises(ValueError, match="kill switch"):
            operation()
    network.assert_not_called()
    store.merge([store.tv("frame").model_copy(update={"enabled": True})])
    assert not store.tv("frame").enabled
    store.set_enabled(True, "frame")
    store.set_enabled(False)
    with pytest.raises(ValueError, match="kill switch"):
        controller.pair("frame")
    store.set_enabled(True)
    assert store.require_enabled("frame").enabled


def test_queued_command_rechecks_kill_switch_after_lock(setup, monkeypatch):
    store, controller = setup
    store.token_path(store.tv("frame")).write_text("test-token")
    original_lock = store.lock

    @contextmanager
    def disable_while_waiting(name):
        if name == "frame":
            store.set_enabled(False, "frame")
        with original_lock(name):
            yield

    monkeypatch.setattr(store, "lock", disable_while_waiting)
    network = MagicMock()
    monkeypatch.setattr(control, "device_info", network)
    with pytest.raises(ValueError, match="kill switch"):
        controller.key("frame", "home")
    network.assert_not_called()
