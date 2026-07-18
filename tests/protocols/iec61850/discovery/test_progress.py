"""Regression tests for IEC 61850 connection/discovery progress snapshots."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.device.protocol.iec61850_handler import IEC61850ClientHandler
from src.proto.iec61850.model import discovery as discovery_module
from src.proto.iec61850.model.discovery import ModelDiscoveryService


def _make_handler(client: Mock) -> IEC61850ClientHandler:
    handler = IEC61850ClientHandler()
    handler._client = client
    return handler


def test_remote_discovery_reports_real_stages_and_keeps_final_snapshot():
    client = Mock(is_connected=True)
    client.connect.return_value = True
    client._discovered_goose_items = []
    client.get_discovered_datasets.return_value = []
    client.reports = None
    client.get_discovered_points.return_value = []

    observed: list[dict] = []

    def discover(*, progress):
        progress("discovering", 0, 2, "发现 LD0")
        observed.append(handler.get_connect_progress())
        progress("discovering", 1, 2, "发现 LD1")
        observed.append(handler.get_connect_progress())
        progress("building", 0, 1, "构建索引")
        observed.append(handler.get_connect_progress())
        return True

    client.remote_discover_model.side_effect = discover
    handler = _make_handler(client)

    assert handler.remote_discover_model() is True

    client.disconnect.assert_called_once_with()
    client.connect.assert_called_once_with(auto_discover=False)
    assert [snapshot["progress"] for snapshot in observed] == [20, 45, 75]
    assert all(snapshot["active"] for snapshot in observed)
    final = handler.get_connect_progress()
    assert final["phase"] == "done"
    assert final["progress"] == 100
    assert final["active"] is False
    assert final["operation"] == "discover"


def test_remote_discovery_exception_finishes_in_failed_state():
    client = Mock(is_connected=True)
    client.connect.return_value = True
    client.remote_discover_model.side_effect = RuntimeError("browse failed")
    handler = _make_handler(client)

    assert handler.remote_discover_model() is False

    progress = handler.get_connect_progress()
    assert progress["phase"] == "failed"
    assert progress["active"] is False
    assert progress["progress"] == 20
    assert progress["message"] == "browse failed"


def test_remote_discovery_stops_when_fresh_mms_association_cannot_be_created():
    client = Mock(is_connected=True)
    client.connect.return_value = False
    handler = _make_handler(client)

    assert handler.remote_discover_model() is False

    client.disconnect.assert_called_once_with()
    client.connect.assert_called_once_with(auto_discover=False)
    client.remote_discover_model.assert_not_called()
    progress = handler.get_connect_progress()
    assert progress["phase"] == "failed"
    assert progress["message"] == "重新建立 MMS 连接失败"


def test_remote_discovery_starts_tls_bridge_before_connecting():
    events = []
    client = Mock(is_connected=True)
    client.connect.side_effect = lambda **kwargs: events.append("connect") or True
    client.remote_discover_model.return_value = False
    handler = _make_handler(client)
    handler._tls_bridge = Mock(last_error=None)
    handler._tls_bridge.start.side_effect = lambda: events.append("tls_start")

    assert handler.remote_discover_model() is False

    assert events[:2] == ["tls_start", "connect"]
    handler._tls_bridge.stop.assert_not_called()


def test_remote_discovery_starts_mms_capture_before_connecting():
    events = []
    client = Mock(is_connected=True)
    client.connect.side_effect = lambda **kwargs: events.append("connect") or True
    client.remote_discover_model.return_value = False
    handler = _make_handler(client)
    handler._mms_capture = Mock(is_running=False)
    handler._mms_capture.start.side_effect = lambda: events.append("capture_start") or True

    assert handler.remote_discover_model() is False

    assert events[:2] == ["capture_start", "connect"]
    handler._mms_capture.start.assert_called_once_with()


def test_remote_discovery_reports_tls_handshake_error():
    client = Mock(is_connected=True)
    client.connect.return_value = False
    logger = Mock()
    handler = IEC61850ClientHandler(log=logger)
    handler._client = client
    handler._tls_bridge = Mock(last_error="certificate verify failed: IP address mismatch")

    assert handler.remote_discover_model() is False

    handler._tls_bridge.start.assert_called_once_with()
    handler._tls_bridge.stop.assert_called_once_with()
    progress = handler.get_connect_progress()
    assert progress["phase"] == "failed"
    assert "certificate verify failed" in progress["message"]
    logger.error.assert_any_call("IEC61850 TLS 握手失败: certificate verify failed: IP address mismatch")


def test_second_progress_task_is_rejected_while_discovery_is_active():
    client = Mock(is_connected=True)
    handler = _make_handler(client)
    handler._begin_progress("discover", handler.PHASE_DISCOVERING, 30, "发现中")

    assert handler.remote_discover_model() is False
    assert handler.get_connect_progress()["progress"] == 30
    client.remote_discover_model.assert_not_called()


def test_variable_spec_probe_uses_circuit_breaker_after_repeated_failures():
    discovery = ModelDiscoveryService()

    with patch.object(discovery, "_query_variable_spec_type", return_value=None) as query:
        for index in range(discovery._variable_spec_failure_limit + 5):
            assert discovery._probe_variable_spec_type(object(), f"LD0/LLN0.Do{index}.stVal", "ST") is None

    assert discovery._variable_spec_disabled is True
    assert query.call_count == discovery._variable_spec_failure_limit


def test_discovery_invalidation_clears_cold_start_caches():
    discovery = ModelDiscoveryService()
    discovery._model = Mock()
    discovery._model_timestamp = 123.0
    discovery._struct_sub_da_cache["LD0/MMXU1.TotW.mag"] = []
    discovery._type_probe_cache[("LD0/MMXU1.TotW.mag.f", "MX")] = Mock()
    discovery._variable_spec_failures = 5
    discovery._variable_spec_disabled = True

    discovery.invalidate()

    assert discovery._model is None
    assert discovery._model_timestamp == 0.0
    assert discovery._struct_sub_da_cache == {}
    assert discovery._type_probe_cache == {}
    assert discovery._variable_spec_failures == 0
    assert discovery._variable_spec_disabled is False


def test_logical_device_discovery_prefers_gil_releasing_wrapper(monkeypatch):
    calls = []
    fake_iec61850 = SimpleNamespace(
        IED_ERROR_OK=0,
        pyWrap_IedConnection_getLogicalDeviceList=lambda conn: calls.append(("safe", conn)) or (["LD0"], 0),
        IedConnection_getLogicalDeviceList=lambda _conn: (_ for _ in ()).throw(
            AssertionError("raw blocking call must not be selected when wrapper exists")
        ),
    )
    monkeypatch.setattr(discovery_module, "iec61850", fake_iec61850, raising=False)
    monkeypatch.setattr(discovery_module, "get_list_from_linked_list", list)
    conn = object()

    assert ModelDiscoveryService._browse_logical_devices(conn) == ["LD0"]
    assert calls == [("safe", conn)]
