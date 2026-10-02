"""Device forms persist endpoints, effective runtime settings, and protected identities."""

import base64
import importlib
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from asyncua import ua
from fastapi import Request
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.data.model  # noqa: F401
from src.data.model.base import Base
from src.data.model.channel import Channel
from src.data.model.channel_configuration import ChannelProtocolParams
from src.data.model.opcua_config import OpcUaConfig
from src.data.model.opcua_feature import OpcUaFeature
from src.data.model.opcua_node import OpcUaNode
from src.data.model.opcua_secret import OpcUaSecret
from src.data.service.channel_service import ChannelService
from src.data.service.opcua_device_configuration_service import OpcUaDeviceConfigurationService as Service
from src.data.service.opcua_security_service import OpcUaSecurityService
from src.device.protocol.runtime_config import normalize_protocol_params
from src.proto.opcua.client import OpcUaClient
from src.proto.opcua.core.security import generate_certificate, validate_application_identity
from src.proto.opcua.server import OpcUaServer
from src.web.api.schemas.channel import (
    ChannelCreateRequest,
    ChannelDetailRequest,
    ChannelUpdateRequest,
    OpcUaDeviceConfigRequest,
)


@pytest.fixture
def database(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    for module in (
        "channel_service",
        "channel_configuration_service",
        "opcua_device_configuration_service",
        "opcua_config_service",
        "opcua_feature_service",
        "opcua_security_service",
        "opcua_node_service",
    ):
        monkeypatch.setattr(importlib.import_module(f"src.data.service.{module}"), "local_session", factory)
    monkeypatch.setattr(importlib.import_module("src.data.dao.channel_dao"), "local_session", factory)
    monkeypatch.setattr(OpcUaSecurityService, "_directory", staticmethod(lambda: tmp_path / "vault"))
    yield factory
    engine.dispose()


def provision(body=None, host="127.0.0.1", role=1, code="UA"):
    body = body or OpcUaDeviceConfigRequest()
    prepared = Service.prepare(body, host, 4840, role)
    _, channel_id = ChannelService.provision_channel(
        code=code,
        name=code,
        group_id=None,
        protocol_type=7,
        conn_type=role,
        protocol_params=None,
        opcua_prepared=prepared,
        ip=host,
        port=4840,
    )
    return channel_id


def test_create_secure_remote_endpoint_with_generated_credentials_and_safe_detail(database):
    channel_id = provision(
        OpcUaDeviceConfigRequest(
            endpoint_path="/factory/",
            mode="SignAndEncrypt",
            generate_certificate=True,
            identity="username",
            username="operator",
            password="top-secret",
            application_uri="urn:test:client",
        ),
        host="192.0.2.10",
    )
    public = Service.public(channel_id)
    assert public["endpoint_path"] == "/factory/"
    assert public["mode"] == "SignAndEncrypt"
    assert public["certificate_configured"] and public["private_key_configured"] and public["password_configured"]
    assert not {"certificate", "private_key", "password"} & public.keys()
    with database() as session:
        config = session.get(OpcUaConfig, channel_id)
        assert config.endpoint_url == "opc.tcp://192.0.2.10:4840/factory/"
        secrets = session.scalars(select(OpcUaSecret).where(OpcUaSecret.channel_id == channel_id)).all()
        assert all("top-secret" not in secret.ciphertext for secret in secrets)
        security = session.get(OpcUaFeature, (channel_id, "security")).config
    validate_application_identity(security, OpcUaSecurityService.secrets(channel_id))


def test_edit_endpoint_and_runtime_preserves_blank_password_and_existing_private_key(database):
    body = OpcUaDeviceConfigRequest(
        mode="SignAndEncrypt", generate_certificate=True, identity="username", username="operator", password="keep-me"
    )
    channel_id = provision(body)
    original = OpcUaSecurityService.secrets(channel_id)
    body = body.model_copy(update={"generate_certificate": False, "password": None, "endpoint_path": "/updated/"})
    prepared = Service.prepare(body, "192.0.2.20", 4841, 1, channel_id)
    params = normalize_protocol_params(7, 1, {"command_timeout_ms": 8000, "session_timeout_ms": 120000})
    Service.update(channel_id, 1, prepared, {"ip": "192.0.2.20", "port": 4841}, params, 1)
    assert OpcUaSecurityService.secrets(channel_id) == original
    with database() as session:
        assert session.get(OpcUaConfig, channel_id).endpoint_url == "opc.tcp://192.0.2.20:4841/updated/"
        assert session.get(Channel, channel_id).ip == "192.0.2.20"
        assert session.get(ChannelProtocolParams, channel_id).params_json["command_timeout_ms"] == 8000


def test_upload_certificate_pair_and_peer_preserves_trust_on_subsequent_edit(database):
    cert, key = generate_certificate("urn:test:upload", "127.0.0.1")
    peer, _ = generate_certificate("urn:test:peer", "127.0.0.1")
    body = OpcUaDeviceConfigRequest(
        mode="SignAndEncrypt",
        application_uri="urn:test:upload",
        certificate=base64.b64encode(cert).decode(),
        private_key=base64.b64encode(key).decode(),
        peer_certificate=base64.b64encode(peer).decode(),
    )
    channel_id = provision(body)
    assert Service.public(channel_id)["trusted_count"] == 1
    body = body.model_copy(update={"certificate": None, "private_key": None, "peer_certificate": None})
    prepared = Service.prepare(body, "127.0.0.1", 4840, 1, channel_id)
    Service.update(channel_id, 1, prepared, {}, None, 1)
    assert Service.public(channel_id)["trusted_count"] == 1


def test_validation_rejects_insecure_remote_endpoints_and_bad_keys_before_persisting(database):
    with pytest.raises(ValueError, match="loopback"):
        Service.prepare(OpcUaDeviceConfigRequest(), "192.0.2.10", 4840, 1)
    cert, _ = generate_certificate("urn:test:upload", "127.0.0.1")
    _, key = generate_certificate("urn:test:other", "127.0.0.1")
    with pytest.raises(ValueError, match="不匹配"):
        Service.prepare(
            OpcUaDeviceConfigRequest(
                mode="SignAndEncrypt",
                application_uri="urn:test:upload",
                certificate=base64.b64encode(cert).decode(),
                private_key=base64.b64encode(key).decode(),
            ),
            "127.0.0.1",
            4840,
            1,
        )
    with database() as session:
        assert session.scalar(select(Channel.id)) is None


def test_generated_identity_participates_in_creation_transaction(database, monkeypatch):
    import src.data.service.opcua_device_configuration_service as module

    monkeypatch.setattr(module, "protect", lambda *_: (_ for _ in ()).throw(ValueError("vault failure")))
    with pytest.raises(ValueError, match="vault failure"):
        provision(OpcUaDeviceConfigRequest(mode="SignAndEncrypt", generate_certificate=True))
    with database() as session:
        assert session.scalar(select(Channel.id)) is None
        assert session.scalar(select(OpcUaConfig.channel_id)) is None
        assert session.scalar(select(OpcUaFeature.channel_id)) is None


def test_edit_cannot_clear_custom_namespace_when_nodes_exist(database):
    channel_id = provision(OpcUaDeviceConfigRequest(namespace_uri="urn:test:custom"), role=2)
    with database() as session, session.begin():
        session.add(
            OpcUaNode(
                channel_id=channel_id,
                node_id="ns=2;s=power",
                namespace_uri="urn:test:custom",
                browse_name="Power",
                data_type="Double",
                initial_value=0.0,
                writable=True,
            )
        )
    with pytest.raises(ValueError, match="命名空间"):
        Service.prepare(OpcUaDeviceConfigRequest(namespace_uri=""), "127.0.0.1", 4840, 2, channel_id)


@pytest.mark.asyncio
async def test_device_api_create_edit_and_detail_share_secure_endpoint_configuration(database, monkeypatch):
    import src.web.api.channel.router as api

    controller = SimpleNamespace(device_list=[], device_map={}, get_device_by_id=lambda _: None)
    request = Request({"type": "http", "app": SimpleNamespace(state=SimpleNamespace(device_controller=controller))})
    builder = MagicMock()
    builder.makeGeneralDevice.return_value = MagicMock()
    monkeypatch.setattr(api, "get_device_builder", lambda *_: builder)
    monkeypatch.setattr(api.PointMappingService, "get_all_mappings", lambda: [])
    reload_instance = AsyncMock()
    monkeypatch.setattr(api, "reload_device_instance", reload_instance)
    create = ChannelCreateRequest(
        code="SECURE",
        name="Secure client",
        protocol_type=7,
        conn_type=1,
        ip="192.0.2.30",
        port=4840,
        opcua_config=OpcUaDeviceConfigRequest(
            mode="SignAndEncrypt", generate_certificate=True, endpoint_path="/created/"
        ),
    )
    result = await api.create_channel(create, request)
    channel_id = result.data["channel_id"]
    detail = await api.get_channel_by_id(ChannelDetailRequest(channel_id=channel_id))
    public = detail.data["opcua_config"]
    assert public["mode"] == "SignAndEncrypt" and public["certificate_configured"]
    assert not {"certificate", "private_key", "password"} & public.keys()
    body = OpcUaDeviceConfigRequest(
        **{key: value for key, value in public.items() if key in OpcUaDeviceConfigRequest.model_fields}
    )
    update = ChannelUpdateRequest(channel_id=channel_id, opcua_config=body, ip="192.0.2.31", port=4841)
    await api.update_channel(update, request)
    reload_instance.assert_awaited_once_with(controller, channel_id, is_start=False)
    with database() as session:
        assert session.get(OpcUaConfig, channel_id).endpoint_url == "opc.tcp://192.0.2.31:4841/created/"
    reload_instance.reset_mock()
    await api.update_channel(update, request)
    reload_instance.assert_not_awaited()


@pytest.mark.parametrize(
    "field,value", [("session_timeout_ms", 999), ("secure_channel_lifetime_ms", True), ("server_name", "")]
)
def test_protocol_specific_parameter_validation(field, value):
    with pytest.raises(ValueError):
        normalize_protocol_params(7, 2 if field == "server_name" else 1, {field: value})


def test_legacy_client_request_timeout_survives_new_parameter_defaults():
    params = normalize_protocol_params(7, 1, {"connect_timeout_ms": 9000})
    assert params["command_timeout_ms"] == 9000
    explicit = normalize_protocol_params(7, 1, {"connect_timeout_ms": 9000, "command_timeout_ms": 5000})
    assert explicit["command_timeout_ms"] == 5000


@pytest.mark.asyncio
async def test_runtime_parameters_reach_real_sdk_sessions_and_server_name():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = OpcUaServer(
        "127.0.0.1",
        port,
        "urn:test:runtime",
        endpoint_path="/runtime/",
        runtime={"server_name": "Configured UA server"},
    )
    client = OpcUaClient(
        server.endpoint_url,
        runtime={"command_timeout_ms": 7500, "session_timeout_ms": 60000, "secure_channel_lifetime_ms": 120000},
    )
    try:
        await server.start()
        await client.start()
        sdk = client._core._client
        assert sdk.uaclient._timeout == 7.5
        assert sdk.session_timeout == 60000
        assert sdk.secure_channel_timeout == 120000
        assert server._core._server.name == "Configured UA server"
        assert (await client.read(f"i={ua.ObjectIds.Server_ServerStatus_State}"))["value"] == 0
    finally:
        await client.stop()
        await server.stop()
