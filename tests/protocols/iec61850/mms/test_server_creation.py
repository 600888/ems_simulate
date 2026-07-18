"""IEC 61850 native server creation compatibility tests."""

import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.proto.iec61850 import iec61850_server as server_module


def _server_with_model(max_connections=5):
    server = object.__new__(server_module.IEC61850Server)
    server._builder = SimpleNamespace(model=object())
    server.max_connections = max_connections
    return server


def test_create_ied_server_uses_config_when_binding_accepts_null_tls(monkeypatch):
    calls = []
    configured_server = object()
    config = object()
    native = SimpleNamespace(
        IedServerConfig_create=lambda: config,
        IedServerConfig_setMaxMmsConnections=lambda value, limit: calls.append(("limit", value, limit)),
        IedServer_createWithConfig=lambda model, tls, value: configured_server,
        IedServer_create=lambda model: pytest.fail("basic creator should not be used"),
        IedServerConfig_destroy=lambda value: calls.append(("destroy", value)),
    )
    monkeypatch.setattr(server_module, "iec61850", native)

    result = _server_with_model(max_connections=12)._create_ied_server()

    assert result is configured_server
    assert calls == [("limit", config, 12), ("destroy", config)]


def test_create_ied_server_falls_back_when_binding_rejects_null_tls(monkeypatch):
    calls = []
    basic_server = object()
    config = object()

    def reject_null_tls(model, tls, value):
        raise TypeError(
            "invalid null reference in method 'IedServer_createWithConfig', argument 2 of type 'TLSConfiguration'"
        )

    native = SimpleNamespace(
        IedServerConfig_create=lambda: config,
        IedServerConfig_setMaxMmsConnections=lambda value, limit: calls.append(("limit", value, limit)),
        IedServer_createWithConfig=reject_null_tls,
        IedServer_create=lambda model: basic_server,
        IedServerConfig_destroy=lambda value: calls.append(("destroy", value)),
    )
    monkeypatch.setattr(server_module, "iec61850", native)

    result = _server_with_model(max_connections=8)._create_ied_server()

    assert result is basic_server
    assert calls == [("limit", config, 8), ("destroy", config)]


def test_create_ied_server_does_not_hide_unrelated_type_errors(monkeypatch):
    config = object()
    destroyed = []

    def fail_for_another_reason(model, tls, value):
        raise TypeError("unexpected model type")

    native = SimpleNamespace(
        IedServerConfig_create=lambda: config,
        IedServerConfig_setMaxMmsConnections=lambda value, limit: None,
        IedServer_createWithConfig=fail_for_another_reason,
        IedServer_create=lambda model: pytest.fail("unrelated errors must not fall back"),
        IedServerConfig_destroy=lambda value: destroyed.append(value),
    )
    monkeypatch.setattr(server_module, "iec61850", native)

    with pytest.raises(TypeError, match="unexpected model type"):
        _server_with_model()._create_ied_server()

    assert destroyed == [config]


def test_configure_authentication_installs_on_current_native_server():
    server = object.__new__(server_module.IEC61850Server)
    server._server = object()
    server._password_authenticator = Mock()

    server._configure_authentication()

    server._password_authenticator.install.assert_called_once_with(server._server)


def test_create_ied_server_enables_file_service_and_sets_basepath(monkeypatch, tmp_path):
    calls = []
    configured_server = object()
    config = object()
    native = SimpleNamespace(
        IedServerConfig_create=lambda: config,
        IedServerConfig_setMaxMmsConnections=lambda value, limit: None,
        IedServerConfig_enableFileService=lambda value, enabled: calls.append(("enable", value, enabled)),
        IedServerConfig_setFileServiceBasePath=lambda value, path: calls.append(("config_path", value, path)),
        IedServer_createWithConfig=lambda model, tls, value: configured_server,
        IedServer_create=lambda model: pytest.fail("basic creator should not be used"),
        IedServer_setFilestoreBasepath=lambda value, path: calls.append(("server_path", value, path)),
        IedServerConfig_destroy=lambda value: None,
    )
    monkeypatch.setattr(server_module, "iec61850", native)
    server = _server_with_model()
    server._files = SimpleNamespace(base_directory=tmp_path.resolve())

    result = server._create_ied_server()

    expected_path = str(tmp_path.resolve()) + os.sep
    assert result is configured_server
    assert calls == [
        ("enable", config, True),
        ("config_path", config, expected_path),
        ("server_path", configured_server, expected_path),
    ]


def test_create_ied_server_uses_original_path_when_file_directory_is_empty(monkeypatch):
    calls = []
    configured_server = object()
    config = object()
    native = SimpleNamespace(
        IedServerConfig_create=lambda: config,
        IedServerConfig_setMaxMmsConnections=lambda value, limit: None,
        IedServerConfig_enableFileService=lambda value, enabled: pytest.fail(
            "empty directory must not configure files"
        ),
        IedServerConfig_setFileServiceBasePath=lambda value, path: pytest.fail(
            "empty directory must not configure files"
        ),
        IedServer_createWithConfig=lambda model, tls, value: configured_server,
        IedServer_create=lambda model: pytest.fail("basic creator should not be used"),
        IedServer_setFilestoreBasepath=lambda value, path: pytest.fail("disabled service has no basepath"),
        IedServerConfig_destroy=lambda value: None,
    )
    monkeypatch.setattr(server_module, "iec61850", native)
    server = _server_with_model()
    server._files = None

    result = server._create_ied_server()

    assert result is configured_server
    assert calls == []
