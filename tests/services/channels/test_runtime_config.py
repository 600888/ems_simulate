from datetime import UTC, datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data.model.base import Base
from src.data.model.channel_configuration import ChannelProtocolParams, ChannelSecurityConfig
import src.data.service.channel_configuration_service as configuration_service_module
from src.data.service.channel_configuration_service import ChannelConfigurationService
from src.device.protocol.runtime_config import get_protocol_param_defaults, normalize_protocol_params
from src.web.api.channel.security import (
    _load_certificate,
    _load_private_key,
    _validate_ca_certificate,
    _validate_pair,
)
from src.web.api.exceptions import ValidationError


def _certificate_and_key(common_name: str = "ems-test"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return certificate, key


def test_modbus_client_defaults_match_existing_runtime_policy():
    values = get_protocol_param_defaults(1, 1)
    assert values["connect_timeout_ms"] == 3000
    assert values["command_timeout_ms"] == 2000
    assert values["command_retry_count"] == 1
    assert values["reconnect_max_attempts"] == -1


def test_iec104_client_defaults_match_modbus_reconnect_policy():
    values = get_protocol_param_defaults(2, 1)
    assert values["send_window_size"] == 12
    assert values["receive_window_size"] == 8
    assert values["t0_timeout_s"] == 10
    assert values["t1_timeout_s"] == 15
    assert values["t2_timeout_s"] == 10
    assert values["t3_interval_s"] == 20
    assert values["originator_address"] == 0
    assert values["clock_sync_interval_s"] == 0
    assert values["general_interrogation_interval_s"] == 0
    assert values["counter_interrogation_interval_s"] == 0
    assert values["general_interrogation_on_connect"] is True
    assert values["counter_interrogation_on_connect"] is True
    assert values["reconnect_initial_interval_ms"] == 2000
    assert values["reconnect_max_interval_ms"] == 30000
    assert values["reconnect_max_attempts"] == -1


def test_reconnect_attempt_semantics_accept_minus_one_and_reject_lower_values():
    values = normalize_protocol_params(2, 1, {"reconnect_max_attempts": -1})
    assert values["reconnect_max_attempts"] == -1

    with pytest.raises(ValueError, match="reconnect_max_attempts"):
        normalize_protocol_params(2, 1, {"reconnect_max_attempts": -2})


def test_server_without_runtime_parameters_rejects_client_fields():
    with pytest.raises(ValueError, match="不支持参数"):
        normalize_protocol_params(1, 2, {"connect_timeout_ms": 3000})


def test_server_runtime_defaults_are_protocol_specific():
    assert get_protocol_param_defaults(1, 2) == {
        "client_idle_timeout_ms": 0,
        "max_connections": 0,
    }
    iec104_defaults = get_protocol_param_defaults(2, 2)
    assert iec104_defaults["send_window_size"] == 12
    assert iec104_defaults["receive_window_size"] == 8
    assert iec104_defaults["t0_timeout_s"] == 3
    assert iec104_defaults["t1_timeout_s"] == 3
    assert iec104_defaults["t2_timeout_s"] == 1
    assert iec104_defaults["t3_interval_s"] == 20
    assert get_protocol_param_defaults(3, 2)["session_idle_timeout_ms"] == 30000
    assert get_protocol_param_defaults(4, 2)["max_connections"] == 5
    assert get_protocol_param_defaults(4, 2)["mms_capture_enabled"] is False
    assert get_protocol_param_defaults(4, 2)["authentication_enabled"] is False
    assert get_protocol_param_defaults(4, 2)["authentication_password"] == ""
    assert get_protocol_param_defaults(4, 2)["file_service_directory"] == ""


def test_iec61850_mms_capture_can_be_disabled():
    client = normalize_protocol_params(4, 1, {"mms_capture_enabled": False})
    server = normalize_protocol_params(4, 2, {"mms_capture_enabled": False})

    assert client["mms_capture_enabled"] is False
    assert server["mms_capture_enabled"] is False


def test_iec61850_association_defaults_match_iedscout():
    values = get_protocol_param_defaults(4, 1)

    assert values["model_discovery_timeout_s"] == 60
    assert values["authentication_enabled"] is False
    assert values["authentication_password"] == ""
    for prefix in ("remote", "local"):
        assert values[f"{prefix}_ap_title"] == "1,1,1,999,1"
        assert values[f"{prefix}_ae_qualifier"] == 12
        assert values[f"{prefix}_p_selector"] == "00 00 00 01"
        assert values[f"{prefix}_s_selector"] == "00 01"
        assert values[f"{prefix}_t_selector"] == "00 01"


def test_iec61850_password_authentication_requires_a_password():
    for conn_type in (1, 2):
        with pytest.raises(ValueError, match="认证密码"):
            normalize_protocol_params(4, conn_type, {"authentication_enabled": True})

    values = normalize_protocol_params(
        4,
        1,
        {
            "authentication_enabled": True,
            "authentication_password": "ied-secret",
            "remote_ap_title": "1.1.1.999.1",
            "remote_p_selector": "00:00:00:01",
        },
    )
    assert values["authentication_password"] == "ied-secret"
    assert values["remote_ap_title"] == "1,1,1,999,1"
    assert values["remote_p_selector"] == "00 00 00 01"


def test_iec104_legacy_millisecond_parameters_are_migrated_to_seconds():
    values = normalize_protocol_params(
        2,
        2,
        {
            "connection_timeout_ms": 3000,
            "message_timeout_ms": 3000,
            "keep_alive_interval_ms": 20000,
        },
    )
    assert values["t0_timeout_s"] == 3
    assert values["t1_timeout_s"] == 3
    assert values["t3_interval_s"] == 20


def test_iec104_link_parameter_relationships_are_validated():
    with pytest.raises(ValueError, match="t2"):
        normalize_protocol_params(2, 1, {"t1_timeout_s": 2, "t2_timeout_s": 3})

    with pytest.raises(ValueError, match="窗口"):
        normalize_protocol_params(2, 1, {"send_window_size": 4, "receive_window_size": 5})


def test_server_connection_limit_is_validated():
    with pytest.raises(ValueError, match="max_connections"):
        normalize_protocol_params(4, 2, {"max_connections": 1001})


def test_channel_protocol_params_are_persisted_across_sessions(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(configuration_service_module, "local_session", session_factory)

    defaults = ChannelConfigurationService.get_protocol_params(501, 1, 2)
    assert defaults["values"]["max_connections"] == 0

    ChannelConfigurationService.save_protocol_params(
        501,
        1,
        2,
        {"client_idle_timeout_ms": 60000, "max_connections": 12},
    )

    with session_factory() as session:
        persisted = session.get(ChannelProtocolParams, 501)
        assert persisted is not None
        assert persisted.params_json == {
            "client_idle_timeout_ms": 60000,
            "max_connections": 12,
        }

    reloaded = ChannelConfigurationService.get_protocol_params(501, 1, 2)
    assert reloaded["values"]["client_idle_timeout_ms"] == 60000
    assert reloaded["values"]["max_connections"] == 12


def test_existing_iec61850_params_persist_new_capture_default(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(configuration_service_module, "local_session", session_factory)

    with session_factory() as session, session.begin():
        session.add(
            ChannelProtocolParams(
                channel_id=61850,
                protocol_type=4,
                conn_type=1,
                schema_version=1,
                params_json={
                    "connect_timeout_ms": 3000,
                    "command_timeout_ms": 3000,
                    "model_discovery_timeout_s": 600,
                },
            )
        )

    loaded = ChannelConfigurationService.get_protocol_params(61850, 4, 1)
    assert loaded["values"]["model_discovery_timeout_s"] == 600
    assert loaded["values"]["mms_capture_enabled"] is False
    assert loaded["values"]["remote_ap_title"] == "1,1,1,999,1"
    assert loaded["values"]["authentication_enabled"] is False

    with session_factory() as session:
        persisted = session.get(ChannelProtocolParams, 61850)
        assert persisted is not None
        assert persisted.params_json["model_discovery_timeout_s"] == 600
        assert persisted.params_json["mms_capture_enabled"] is False
        assert persisted.params_json["remote_p_selector"] == "00 00 00 01"
        assert persisted.params_json["authentication_password"] == ""


def test_iec61850_association_and_authentication_are_persisted(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(configuration_service_module, "local_session", session_factory)

    saved = ChannelConfigurationService.save_protocol_params(
        61851,
        4,
        1,
        {
            **get_protocol_param_defaults(4, 1),
            "authentication_enabled": True,
            "authentication_password": "ied-secret",
            "remote_ap_title": "1.3.9999.23",
            "local_t_selector": "00:02",
        },
    )
    assert saved["values"]["remote_ap_title"] == "1,3,9999,23"
    assert saved["values"]["local_t_selector"] == "00 02"

    reloaded = ChannelConfigurationService.get_protocol_params(61851, 4, 1)
    assert reloaded["values"]["authentication_enabled"] is True
    assert reloaded["values"]["authentication_password"] == "ied-secret"
    assert reloaded["values"]["remote_ap_title"] == "1,3,9999,23"


def test_iec61850_server_password_authentication_is_persisted(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(configuration_service_module, "local_session", session_factory)

    ChannelConfigurationService.save_protocol_params(
        61852,
        4,
        2,
        {
            **get_protocol_param_defaults(4, 2),
            "authentication_enabled": True,
            "authentication_password": "server-secret",
        },
    )

    reloaded = ChannelConfigurationService.get_protocol_params(61852, 4, 2)
    assert reloaded["values"]["authentication_enabled"] is True
    assert reloaded["values"]["authentication_password"] == "server-secret"


def test_iec61850_server_file_service_directory_is_persisted(monkeypatch, tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(configuration_service_module, "local_session", session_factory)
    selected_directory = str(tmp_path / "ied-files")

    ChannelConfigurationService.save_protocol_params(
        61853,
        4,
        2,
        {
            **get_protocol_param_defaults(4, 2),
            "file_service_directory": selected_directory,
        },
    )

    reloaded = ChannelConfigurationService.get_protocol_params(61853, 4, 2)
    assert reloaded["values"]["file_service_directory"] == selected_directory


def test_tls_mode_is_persisted_and_exposed_to_runtime(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(configuration_service_module, "local_session", session_factory)

    ChannelConfigurationService.save_security_config(
        502,
        tls_enabled=True,
        tls_mode="basic",
        certificate_path="certificate.pem",
        certificate_filename="certificate.pem",
        private_key_path="private_key.pem",
        private_key_filename="private_key.pem",
    )

    with session_factory() as session:
        persisted = session.get(ChannelSecurityConfig, 502)
        assert persisted is not None
        assert persisted.tls_mode == "basic"

    persisted_public = ChannelConfigurationService.get_security_config(502)
    persisted_runtime = ChannelConfigurationService.get_runtime_security(502)
    assert persisted_public["tls_enabled"] is True
    assert persisted_public["tls_mode"] == "basic"
    assert persisted_runtime["tls_enabled"] is True
    assert persisted_runtime["tls_mode"] == "basic"


def test_clone_for_channel_persists_protocol_tls_and_independent_files(monkeypatch, tmp_path):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(configuration_service_module, "local_session", session_factory)
    monkeypatch.setattr(configuration_service_module, "get_storage_path", lambda _name: str(tmp_path))

    source_dir = tmp_path / "security" / "2"
    source_dir.mkdir(parents=True)
    certificate = source_dir / "certificate.pem"
    private_key = source_dir / "private_key.pem"
    certificate.write_bytes(b"certificate-data")
    private_key.write_bytes(b"private-key-data")

    source_protocol = {
        **get_protocol_param_defaults(2, 1),
        "originator_address": 7,
        "reconnect_max_attempts": 9,
    }
    ChannelConfigurationService.save_protocol_params(2, 2, 1, source_protocol)
    ChannelConfigurationService.save_security_config(
        2,
        tls_enabled=True,
        tls_mode="basic",
        certificate_path=str(certificate),
        certificate_filename="client.crt",
        private_key_path=str(private_key),
        private_key_filename="client.key",
    )

    ChannelConfigurationService.clone_for_channel(2, 30, 2, 1)

    cloned_protocol = ChannelConfigurationService.get_protocol_params(30, 2, 1)
    cloned_security = ChannelConfigurationService.get_runtime_security(30)
    cloned_public_security = ChannelConfigurationService.get_security_config(30)
    assert cloned_protocol["values"] == source_protocol
    assert cloned_security["tls_enabled"] is True
    assert cloned_security["tls_mode"] == "basic"
    assert cloned_public_security["certificate_filename"] == "client.crt"
    assert cloned_public_security["private_key_filename"] == "client.key"
    assert cloned_security["certificate_path"] != str(certificate)
    assert cloned_security["private_key_path"] != str(private_key)
    assert (tmp_path / "security" / "30" / "certificate.pem").read_bytes() == b"certificate-data"
    assert (tmp_path / "security" / "30" / "private_key.pem").read_bytes() == b"private-key-data"


def test_reconnect_maximum_must_not_be_less_than_initial_interval():
    with pytest.raises(ValueError, match="最大间隔"):
        normalize_protocol_params(
            1,
            1,
            {
                **get_protocol_param_defaults(1, 1),
                "reconnect_initial_interval_ms": 5000,
                "reconnect_max_interval_ms": 1000,
            },
        )


def test_certificate_and_private_key_pair_validation():
    certificate, key = _certificate_and_key()
    parsed_certificate = _load_certificate(certificate.public_bytes(serialization.Encoding.PEM))
    parsed_key = _load_private_key(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    _validate_pair(parsed_certificate, parsed_key)


def test_mismatched_certificate_and_private_key_are_rejected():
    certificate, _ = _certificate_and_key("certificate")
    _, other_key = _certificate_and_key("private-key")
    with pytest.raises(ValidationError, match="不匹配"):
        _validate_pair(certificate, other_key)


def test_identity_certificate_is_rejected_as_ca_certificate():
    certificate, _ = _certificate_and_key("identity")
    with pytest.raises(ValidationError, match="Basic Constraints"):
        _validate_ca_certificate(certificate)
