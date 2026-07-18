"""Regression tests for explicit IEC 61850 remote model discovery."""

from unittest.mock import Mock, patch

from src.proto.iec61850.iec61850_client import IEC61850Client
from src.proto.iec61850.model.ied_model import IedModel, LDModel


def test_fill_du_names_applies_one_do_description_to_all_child_points():
    client = IEC61850Client.__new__(IEC61850Client)
    client._registry = Mock()
    client._discovery = Mock()
    client._discovery.description_da_names.return_value = None
    client._read_du_description = Mock(return_value="总有功功率")
    discovered = [
        {"address": "LD0/MMXU1.TotW.mag.f"},
        {"address": "LD0/MMXU1.TotW.q"},
    ]

    client._fill_du_names(discovered)

    client._read_du_description.assert_called_once_with("LD0/MMXU1.TotW")
    assert [point["name"] for point in discovered] == ["总有功功率", "总有功功率"]
    assert client._registry.set_name.call_count == 2


def test_fill_du_names_skips_reads_when_directory_has_no_description_da():
    client = IEC61850Client.__new__(IEC61850Client)
    client._registry = Mock()
    client._discovery = Mock()
    client._discovery.description_da_names.return_value = ()
    client._read_du_description = Mock(return_value="")
    discovered = [{"address": "LD0/MMXU1.TotW.mag.f"}]

    client._fill_du_names(discovered)

    client._read_du_description.assert_not_called()


def test_fill_du_names_prefers_batch_description_values():
    client = IEC61850Client.__new__(IEC61850Client)
    client._registry = Mock()
    client._discovery = Mock()
    client._discovery.description_da_names.return_value = ("dU",)
    client._read_du_description = Mock(return_value="不应单点读取")
    datamodels = Mock()
    datamodels._read_du_descriptions_batch.return_value = {"LD0/MMXU1.TotW": "总有功功率"}
    client._plugins = Mock()
    client._plugins.get.return_value = datamodels
    discovered = [{"address": "LD0/MMXU1.TotW.mag.f"}]

    client._fill_du_names(discovered)

    datamodels._read_du_descriptions_batch.assert_called_once_with({"LD0/MMXU1.TotW": ("dU",)})
    client._read_du_description.assert_not_called()
    assert discovered[0]["name"] == "总有功功率"


def test_remote_discovery_forces_online_refresh_and_replaces_registry():
    client = IEC61850Client.__new__(IEC61850Client)
    client.ip = "127.0.0.1"
    client.port = 102
    client._conn = Mock(is_connected=True)
    client._conn._discovered_lds = ["OLD_LD"]
    client._report_conn = Mock()
    client._report_conn._discovered_lds = ["OLD_REPORT_LD"]
    fresh_model = Mock()
    client._discovery = Mock()
    client._discovery.discover.return_value = fresh_model
    client._registry = Mock()
    client._last_import_result = Mock()
    client._offline_model_source = "cache"
    client._rcbs_from_icd = [{"ref": "OLD/LLN0.rp01"}]
    client._fill_du_names = Mock()
    cache = Mock()
    discovered = [{"address": "LD0/MMXU1.TotW.mag.f"}]

    with (
        patch("src.proto.iec61850.model.ModelCache.instance", return_value=cache),
        patch("src.proto.iec61850.model.registry_bridge.build_registry_from_model") as build_registry,
    ):
        build_registry.return_value = discovered
        assert client.remote_discover_model() is True

    cache.invalidate.assert_called_once_with("127.0.0.1:102")
    cache.get.assert_not_called()
    client._discovery.invalidate.assert_called_once_with()
    client._registry.clear.assert_called_once_with()
    assert client._conn._discovered_lds == []
    assert client._report_conn._discovered_lds == []
    assert client._last_import_result is None
    assert client._offline_model_source is None
    assert client._rcbs_from_icd == []
    client._discovery.discover.assert_called_once_with(client._conn, progress=None)
    cache.set.assert_called_once_with("127.0.0.1:102", fresh_model)
    build_registry.assert_called_once_with(fresh_model, client._registry)
    client._fill_du_names.assert_called_once_with(discovered, progress=None)


def test_remote_discovery_can_reuse_cache_for_internal_callers():
    client = IEC61850Client.__new__(IEC61850Client)
    client.ip = "127.0.0.1"
    client.port = 102
    client._conn = Mock(is_connected=True)
    client._conn.browse_logical_devices.return_value = ["LD0"]
    client._discovery = Mock()
    client._registry = Mock()
    client._fill_du_names = Mock()
    cached_model = IedModel(lds=(LDModel(name="LD0"),))
    cache = Mock()
    cache.get.return_value = cached_model
    discovered = [{"address": "LD0/MMXU1.TotW.mag.f"}]

    with (
        patch("src.proto.iec61850.model.ModelCache.instance", return_value=cache),
        patch("src.proto.iec61850.model.registry_bridge.build_registry_from_model") as build_registry,
    ):
        build_registry.return_value = discovered
        assert client.remote_discover_model(force_refresh=False) is True

    cache.invalidate.assert_not_called()
    client._discovery.invalidate.assert_not_called()
    client._discovery.discover.assert_not_called()
    build_registry.assert_called_once_with(cached_model, client._registry)
    client._fill_du_names.assert_called_once_with(discovered)
