"""Regression tests for explicit IEC 61850 remote model discovery."""

from unittest.mock import Mock, patch

from src.proto.iec61850.iec61850_client import IEC61850Client


def test_fill_du_names_applies_one_do_description_to_all_child_points():
    client = IEC61850Client.__new__(IEC61850Client)
    client._registry = Mock()
    client._read_du_description = Mock(return_value="总有功功率")
    discovered = [
        {"address": "LD0/MMXU1.TotW.mag.f"},
        {"address": "LD0/MMXU1.TotW.q"},
    ]

    client._fill_du_names(discovered)

    client._read_du_description.assert_called_once_with("LD0/MMXU1.TotW")
    assert [point["name"] for point in discovered] == ["总有功功率", "总有功功率"]
    assert client._registry.set_name.call_count == 2


def test_remote_discovery_forces_online_refresh_and_replaces_registry():
    client = IEC61850Client.__new__(IEC61850Client)
    client.ip = "127.0.0.1"
    client.port = 102
    client._conn = Mock(is_connected=True)
    fresh_model = Mock()
    client._discovery = Mock()
    client._discovery.discover.return_value = fresh_model
    client._registry = Mock()
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
    client._discovery.discover.assert_called_once_with(client._conn, progress=None)
    cache.set.assert_called_once_with("127.0.0.1:102", fresh_model)
    build_registry.assert_called_once_with(fresh_model, client._registry)
    client._fill_du_names.assert_called_once_with(discovered)


def test_remote_discovery_can_reuse_cache_for_internal_callers():
    client = IEC61850Client.__new__(IEC61850Client)
    client.ip = "127.0.0.1"
    client.port = 102
    client._conn = Mock(is_connected=True)
    client._discovery = Mock()
    client._registry = Mock()
    client._fill_du_names = Mock()
    cached_model = Mock()
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
