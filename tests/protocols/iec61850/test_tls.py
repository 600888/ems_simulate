"""IEC 61850 native TLS configuration tests."""

from datetime import UTC, datetime, timedelta
import ipaddress

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import pytest

from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler
from src.proto.iec61850.tls import (
    IEC61850TlsConfigurationError,
    create_client_tls_configuration,
    create_server_tls_configuration,
)


def _certificate(subject, issuer, public_key, issuer_key, *, ca=False, eku=None, san=False):
    now = datetime.now(UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)]))
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    )
    if eku:
        builder = builder.add_extension(x509.ExtendedKeyUsage([eku]), critical=False)
    if san:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
    return builder.sign(issuer_key, hashes.SHA256())


@pytest.fixture
def tls_files(tmp_path):
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "IEC61850 test CA")])
    ca = _certificate("IEC61850 test CA", ca_name, ca_key.public_key(), ca_key, ca=True)

    paths = {}
    ca_path = tmp_path / "ca.pem"
    ca_path.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    paths["ca"] = str(ca_path)
    for name, eku, san in (
        ("server", ExtendedKeyUsageOID.SERVER_AUTH, True),
        ("client", ExtendedKeyUsageOID.CLIENT_AUTH, False),
    ):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cert = _certificate(name, ca.subject, key.public_key(), ca_key, eku=eku, san=san)
        cert_path = tmp_path / f"{name}.pem"
        key_path = tmp_path / f"{name}.key"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        paths[f"{name}_cert"] = str(cert_path)
        paths[f"{name}_key"] = str(key_path)
    return paths


def _settings(files, identity, mode):
    return {
        "tls_enabled": True,
        "tls_mode": mode,
        "certificate_path": files[f"{identity}_cert"],
        "private_key_path": files[f"{identity}_key"],
        "ca_certificate_path": files["ca"] if mode == "mutual" else None,
    }


def test_mutual_tls_requires_ca(tls_files):
    settings = _settings(tls_files, "client", "mutual")
    settings["ca_certificate_path"] = None
    with pytest.raises(IEC61850TlsConfigurationError, match="CA 证书"):
        create_client_tls_configuration(settings)


def test_basic_tls_configurations_load_without_ca(tls_files):
    server = create_server_tls_configuration(_settings(tls_files, "server", "basic"))
    client = create_client_tls_configuration(_settings(tls_files, "client", "basic"))
    try:
        assert server is not None and server.native is not None
        assert client is not None and client.native is not None
    finally:
        client.close()
        server.close()


def test_basic_tls_requires_1619_insecure_api(tls_files, monkeypatch):
    from pyiec61850 import pyiec61850 as iec61850

    monkeypatch.delattr(iec61850, "TLSConfiguration_setInsecure")
    with pytest.raises(IEC61850TlsConfigurationError, match="1.6.1.9"):
        create_client_tls_configuration(_settings(tls_files, "client", "basic"))


def test_client_handler_passes_native_tls_to_direct_mms_connection(tls_files, monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("src.proto.iec61850.iec61850_client.IEC61850Client", FakeClient)
    handler = IEC61850ClientHandler()
    handler.initialize(
        {
            "ip": "127.0.0.1",
            "port": 18102,
            "runtime": {"mms_capture_enabled": True},
            "security": _settings(tls_files, "client", "mutual"),
        }
    )

    assert captured["ip"] == "127.0.0.1"
    assert captured["port"] == 18102
    assert captured["tls_configuration"] is handler._tls_configuration
    assert handler._tls_configuration.native is not None
    assert handler._mms_capture.port == 18102


def test_server_handler_passes_native_tls_to_public_mms_endpoint(tls_files, monkeypatch):
    captured = {}

    class FakeServer:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("src.proto.iec61850.iec61850_server.IEC61850Server", FakeServer)
    handler = IEC61850ServerHandler()
    handler.initialize(
        {
            "ip": "0.0.0.0",
            "port": 18102,
            "runtime": {"mms_capture_enabled": True},
            "security": _settings(tls_files, "server", "mutual"),
        }
    )

    assert captured["ip"] == "0.0.0.0"
    assert captured["port"] == 18102
    assert captured["tls_configuration"] is handler._tls_configuration
    assert handler._tls_configuration.native is not None
    assert handler._mms_capture.port == 18102


def test_client_handler_does_not_create_capture_when_disabled(monkeypatch):
    class FakeClient:
        def __init__(self, **kwargs):
            pass

    monkeypatch.setattr("src.proto.iec61850.iec61850_client.IEC61850Client", FakeClient)
    handler = IEC61850ClientHandler()
    handler.initialize(
        {
            "ip": "127.0.0.1",
            "port": 102,
            "runtime": {"mms_capture_enabled": False},
        }
    )

    assert handler._mms_capture is None


def test_server_handler_does_not_create_capture_when_disabled(monkeypatch):
    class FakeServer:
        def __init__(self, **kwargs):
            pass

    monkeypatch.setattr("src.proto.iec61850.iec61850_server.IEC61850Server", FakeServer)
    handler = IEC61850ServerHandler()
    handler.initialize(
        {
            "ip": "0.0.0.0",
            "port": 102,
            "runtime": {"mms_capture_enabled": False},
        }
    )

    assert handler._mms_capture is None


def test_server_handler_passes_password_authentication_to_native_server(monkeypatch):
    captured = {}

    class FakeServer:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("src.proto.iec61850.iec61850_server.IEC61850Server", FakeServer)
    handler = IEC61850ServerHandler()
    handler.initialize(
        {
            "ip": "0.0.0.0",
            "port": 102,
            "runtime": {
                "authentication_enabled": True,
                "authentication_password": "server-secret",
                "file_service_directory": "D:/ied-files",
            },
        }
    )

    assert captured["authentication_enabled"] is True
    assert captured["authentication_password"] == "server-secret"
    assert captured["file_service_directory"] == "D:/ied-files"


def test_native_mutual_tls_configurations_load(tls_files):
    server = create_server_tls_configuration(_settings(tls_files, "server", "mutual"))
    client = create_client_tls_configuration(_settings(tls_files, "client", "mutual"))
    try:
        assert server is not None and server.native is not None
        assert client is not None and client.native is not None
    finally:
        client.close()
        server.close()
