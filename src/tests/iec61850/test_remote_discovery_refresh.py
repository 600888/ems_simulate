"""Regression tests for explicit IEC 61850 remote model discovery."""

from unittest.mock import Mock, patch

from src.proto.iec61850.iec61850_client import IEC61850Client


def test_remote_discovery_forces_online_refresh_and_replaces_registry():
    client = IEC61850Client.__new__(IEC61850Client)
    client.ip = "127.0.0.1"
    client.port = 102
    client._conn = Mock(is_connected=True)
    fresh_model = Mock()
    client._discovery = Mock()
    client._discovery.discover.return_value = fresh_model
    client._registry = Mock()
    cache = Mock()

    with (
        patch("src.proto.iec61850.model.ModelCache.instance", return_value=cache),
        patch("src.proto.iec61850.model.registry_bridge.build_registry_from_model") as build_registry,
    ):
        assert client.remote_discover_model() is True

    cache.invalidate.assert_called_once_with("127.0.0.1:102")
    cache.get.assert_not_called()
    client._discovery.invalidate.assert_called_once_with()
    client._discovery.discover.assert_called_once_with(client._conn)
    cache.set.assert_called_once_with("127.0.0.1:102", fresh_model)
    build_registry.assert_called_once_with(fresh_model, client._registry)


def test_remote_discovery_can_reuse_cache_for_internal_callers():
    client = IEC61850Client.__new__(IEC61850Client)
    client.ip = "127.0.0.1"
    client.port = 102
    client._conn = Mock(is_connected=True)
    client._discovery = Mock()
    client._registry = Mock()
    cached_model = Mock()
    cache = Mock()
    cache.get.return_value = cached_model

    with (
        patch("src.proto.iec61850.model.ModelCache.instance", return_value=cache),
        patch("src.proto.iec61850.model.registry_bridge.build_registry_from_model") as build_registry,
    ):
        assert client.remote_discover_model(force_refresh=False) is True

    cache.invalidate.assert_not_called()
    client._discovery.invalidate.assert_not_called()
    client._discovery.discover.assert_not_called()
    build_registry.assert_called_once_with(cached_model, client._registry)
