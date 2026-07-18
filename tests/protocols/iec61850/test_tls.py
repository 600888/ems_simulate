"""IEC 61850 TLS configuration and transport bridge tests."""

from datetime import UTC, datetime, timedelta
import ipaddress
import socket
import threading

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import pytest

from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler
from src.proto.iec61850.tls import (
    IEC61850TlsConfigurationError,
    TlsClientBridge,
    TlsServerBridge,
    allocate_loopback_port,
    create_client_context,
    create_server_context,
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
        create_client_context(settings)


def test_client_handler_routes_native_mms_through_loopback_bridge(tls_files, monkeypatch):
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
            "security": _settings(tls_files, "client", "basic"),
        }
    )

    assert captured["ip"] == "127.0.0.1"
    assert captured["port"] == handler._tls_bridge.local_port
    assert captured["nonblocking_connect"] is True
    assert handler._tls_bridge.remote_port == 18102
    assert handler._mms_capture.port == handler._tls_bridge.local_port


def test_server_handler_keeps_native_mms_on_loopback(tls_files, monkeypatch):
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

    assert captured["ip"] == "127.0.0.1"
    assert captured["port"] == handler._tls_bridge.backend_port
    assert handler._tls_bridge.listen_port == 18102
    assert handler._mms_capture.port == handler._tls_bridge.backend_port


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


@pytest.mark.parametrize("mode", ["basic", "mutual"])
def test_tls_bridges_encrypt_and_relay_bidirectionally(tls_files, mode):
    backend_port = allocate_loopback_port()
    external_port = allocate_loopback_port()
    ready = threading.Event()

    def echo_server():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", backend_port))
            listener.listen(1)
            ready.set()
            connection, _ = listener.accept()
            with connection:
                connection.sendall(connection.recv(1024))

    threading.Thread(target=echo_server, daemon=True).start()
    assert ready.wait(2)
    server = TlsServerBridge(
        "127.0.0.1",
        external_port,
        backend_port,
        create_server_context(_settings(tls_files, "server", mode)),
    )
    client = TlsClientBridge(
        "127.0.0.1",
        external_port,
        create_client_context(_settings(tls_files, "client", mode)),
    )
    server.start()
    client.start()
    try:
        with socket.create_connection(("127.0.0.1", client.local_port), timeout=3) as connection:
            connection.sendall(b"IEC61850-MMS")
            assert connection.recv(1024) == b"IEC61850-MMS"
        assert client.last_error is None
        assert server.last_error is None
    finally:
        client.stop()
        server.stop()
