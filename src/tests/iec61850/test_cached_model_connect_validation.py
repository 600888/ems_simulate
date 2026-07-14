"""缓存模型在 MMS 连接建立后的校验时序回归测试。"""

from unittest.mock import Mock, patch

from src.device.protocol.iec61850_handler import IEC61850ClientHandler
from src.proto.iec61850.iec61850_client import IEC61850Client
from src.proto.iec61850.model.ied_model import IedModel, LDModel


def test_client_invalidates_loaded_cache_only_after_online_mismatch():
    client = IEC61850Client.__new__(IEC61850Client)
    client.ip = "127.0.0.1"
    client.port = 102
    client._offline_model_source = "cache"
    client._conn = Mock(is_connected=True)
    client._conn.browse_logical_devices.return_value = ["PCS01PIGO"]
    client._discovery = Mock()
    client._discovery.model = IedModel(lds=(LDModel(name="LC001RACK06"),))
    client._registry = Mock()
    client._rcbs_from_icd = []
    cache = Mock()

    with patch("src.proto.iec61850.model.ModelCache.instance", return_value=cache):
        assert client.validate_loaded_offline_model() is False

    cache.invalidate.assert_called_once_with("127.0.0.1:102")
    client._discovery.invalidate.assert_called_once_with()
    client._registry.clear.assert_called_once_with()
    assert client.loaded_from_model_cache is False


def test_client_rejects_local_model_without_deleting_persistent_cache():
    client = IEC61850Client.__new__(IEC61850Client)
    client.ip = "127.0.0.1"
    client.port = 102
    client._offline_model_source = "local"
    client._conn = Mock(is_connected=True)
    client._conn.browse_logical_devices.return_value = ["PCS01PIGO"]
    client._discovery = Mock()
    client._discovery.model = IedModel(lds=(LDModel(name="LC001RACK06"),))
    client._registry = Mock()
    client._rcbs_from_icd = [{"ref": "LC001RACK06/LLN0.rp01"}]

    with patch("src.proto.iec61850.model.ModelCache.instance") as cache_factory:
        assert client.validate_loaded_offline_model() is False

    cache_factory.assert_not_called()
    client._discovery.invalidate.assert_called_once_with()
    client._registry.clear.assert_called_once_with()
    assert client._rcbs_from_icd == []
    assert client.offline_model_requires_validation is False


def test_client_accepts_matching_imported_model():
    client = IEC61850Client.__new__(IEC61850Client)
    client._offline_model_source = "import"
    client._conn = Mock(is_connected=True)
    client._conn.browse_logical_devices.return_value = ["LD0"]
    client._report_conn = Mock()
    client._discovery = Mock()
    client._discovery.model = IedModel(lds=(LDModel(name="LD0"),))

    assert client.validate_loaded_offline_model() is True
    assert client._conn._discovered_lds == ["LD0"]
    assert client._report_conn._discovered_lds == ["LD0"]
    client._discovery.invalidate.assert_not_called()


def test_handler_primes_offline_rcbs_after_connection_and_validation():
    handler = IEC61850ClientHandler(log=Mock())
    reports = Mock()
    reports.restore_cached_rcbs.return_value = True
    client = Mock()
    client.connect.return_value = True
    client.offline_model_requires_validation = True
    client.validate_loaded_offline_model.return_value = True
    client.reports = reports
    handler._client = client
    handler._model_loaded = True
    handler._discovered_rcbs = [{"ref": "LD0/LLN0.rp01", "rcb_type": "URCB"}]

    assert handler.connect() is True

    client.validate_loaded_offline_model.assert_called_once_with()
    reports.restore_cached_rcbs.assert_called_once_with(handler._discovered_rcbs)
    client.disconnect.assert_not_called()


def test_handler_rejects_connection_when_loaded_offline_model_mismatches():
    handler = IEC61850ClientHandler(log=Mock())
    client = Mock()
    client.connect.return_value = True
    client.offline_model_requires_validation = True
    client.validate_loaded_offline_model.return_value = False
    handler._client = client
    handler._model_loaded = True
    handler._discovered_rcbs = [{"ref": "OLD/LLN0.rp01"}]

    assert handler.connect() is False

    client.disconnect.assert_called_once_with()
    assert handler.model_loaded is False
    assert handler._discovered_rcbs == []
    assert handler._connect_phase == handler.PHASE_FAILED
    assert handler._progress_error_code == "model_mismatch"
    assert "离线模型与当前 IEC61850 服务端不匹配" in handler._progress_message


def test_handler_exposes_specific_reason_when_server_connection_fails():
    handler = IEC61850ClientHandler(log=Mock())
    client = Mock()
    client.connect.return_value = False
    handler._client = client

    assert handler.connect() is False

    progress = handler.get_connect_progress()
    assert progress["error_code"] == "connection_failed"
    assert progress["message"] == "无法连接 IEC61850 服务端，请检查 IP、端口和服务状态"
