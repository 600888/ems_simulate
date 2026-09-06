import asyncio
from datetime import UTC, datetime, timedelta
import socket
import ssl

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import pytest

from src.proto.dnp3.dnp3_client import Dnp3Client
from src.proto.dnp3.dnp3_server import Dnp3Server
from src.proto.dnp3.tls import (
    Dnp3TlsConfigurationError,
    create_client_ssl_context,
    create_server_ssl_context,
)


def _create_ca():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "DNP3 Test CA")])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return key, certificate


def _write_identity(tmp_path, name, ca_key, ca_certificate, eku):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
        .issuer_name(ca_certificate.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([eku]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    certificate_path = tmp_path / f"{name}.pem"
    private_key_path = tmp_path / f"{name}.key"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    private_key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return str(certificate_path), str(private_key_path)


@pytest.fixture
def tls_files(tmp_path):
    ca_key, ca_certificate = _create_ca()
    ca_path = tmp_path / "ca.pem"
    ca_path.write_bytes(ca_certificate.public_bytes(serialization.Encoding.PEM))
    server_certificate, server_key = _write_identity(
        tmp_path, "server", ca_key, ca_certificate, ExtendedKeyUsageOID.SERVER_AUTH
    )
    client_certificate, client_key = _write_identity(
        tmp_path, "client", ca_key, ca_certificate, ExtendedKeyUsageOID.CLIENT_AUTH
    )
    return {
        "ca": str(ca_path),
        "server_certificate": server_certificate,
        "server_key": server_key,
        "client_certificate": client_certificate,
        "client_key": client_key,
    }


def _settings(tls_files, role, mode):
    return {
        "tls_enabled": True,
        "tls_mode": mode,
        "certificate_path": tls_files[f"{role}_certificate"] if mode == "mutual" or role == "server" else None,
        "private_key_path": tls_files[f"{role}_key"] if mode == "mutual" or role == "server" else None,
        "ca_certificate_path": tls_files["ca"] if mode == "mutual" or role == "client" else None,
    }


def test_tls_contexts_match_shared_one_way_and_mutual_semantics(tls_files):
    one_way_client = create_client_ssl_context(_settings(tls_files, "client", "one_way"))
    one_way_server = create_server_ssl_context(_settings(tls_files, "server", "one_way"))
    mutual_client = create_client_ssl_context(_settings(tls_files, "client", "mutual"))
    mutual_server = create_server_ssl_context(_settings(tls_files, "server", "mutual"))

    assert one_way_client is not None
    assert one_way_client.minimum_version == ssl.TLSVersion.TLSv1_2
    assert one_way_client.maximum_version == ssl.TLSVersion.TLSv1_2
    assert one_way_client.check_hostname is False
    assert one_way_client.verify_mode == ssl.CERT_REQUIRED
    assert one_way_server is not None and one_way_server.verify_mode == ssl.CERT_NONE
    assert mutual_client is not None and mutual_client.verify_mode == ssl.CERT_REQUIRED
    assert mutual_server is not None and mutual_server.verify_mode == ssl.CERT_REQUIRED


@pytest.mark.parametrize(
    ("tls_version", "expected_version"),
    [
        ("1.2", ssl.TLSVersion.TLSv1_2),
        ("1.3", ssl.TLSVersion.TLSv1_3),
    ],
)
def test_tls_version_pins_client_and_server_contexts(tls_files, tls_version, expected_version):
    client = create_client_ssl_context({**_settings(tls_files, "client", "one_way"), "tls_version": tls_version})
    server = create_server_ssl_context({**_settings(tls_files, "server", "one_way"), "tls_version": tls_version})

    assert client is not None
    assert client.minimum_version == expected_version
    assert client.maximum_version == expected_version
    assert server is not None
    assert server.minimum_version == expected_version
    assert server.maximum_version == expected_version


def test_tls_version_rejects_unsupported_value(tls_files):
    with pytest.raises(Dnp3TlsConfigurationError, match="版本"):
        create_client_ssl_context({**_settings(tls_files, "client", "one_way"), "tls_version": "1.1"})


def test_tls_rejects_missing_material_and_invalid_mode(tls_files):
    with pytest.raises(Dnp3TlsConfigurationError, match="CA 证书"):
        create_client_ssl_context({"tls_enabled": True, "tls_mode": "one_way"})
    with pytest.raises(Dnp3TlsConfigurationError, match="模式"):
        create_server_ssl_context({**_settings(tls_files, "server", "one_way"), "tls_mode": "unknown"})


@pytest.mark.parametrize("tls_mode", ["one_way", "mutual"])
def test_dnp3_master_and_outstation_connect_with_tls(tls_files, tls_mode):
    async def scenario():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        server = Dnp3Server()
        server.set_server_ip("127.0.0.1")
        server.set_server_port(port)
        server.set_ssl_context(create_server_ssl_context(_settings(tls_files, "server", tls_mode)))
        server.add_analog_input(7)
        server.update_analog_input(7, 12.5)

        client = Dnp3Client()
        client.set_server_ip("127.0.0.1")
        client.set_server_port(port)
        client.set_ssl_context(create_client_ssl_context(_settings(tls_files, "client", tls_mode)))
        try:
            assert await server.start() is True
            assert await client.start() is True
            assert client.is_connected is True
            assert await client.read_point_active(7, 30) == pytest.approx(12.5)
            assert server._server is not None
            assert server._server.security["tls"] is True
            assert server._server.security["version"] in {"TLSv1.2", "TLSv1.3"}
        finally:
            await client.stop()
            await server.stop()

    asyncio.run(scenario())


def test_plain_dnp3_client_is_rejected_by_tls_outstation(tls_files):
    async def scenario():
        server = Dnp3Server()
        server.set_server_ip("127.0.0.1")
        server.set_server_port(0)
        server.set_ssl_context(create_server_ssl_context(_settings(tls_files, "server", "one_way")))
        assert await server.start() is True
        assert server._server is not None and server._server._server is not None
        port = server._server._server.sockets[0].getsockname()[1]

        client = Dnp3Client()
        client.set_server_ip("127.0.0.1")
        client.set_server_port(port)
        client.set_parameters(connection_timeout_ms=2000, link_confirm_timeout_ms=1500, reconnect_max_attempts=0)
        try:
            started_at = asyncio.get_running_loop().time()
            assert await client.start() is False
            elapsed = asyncio.get_running_loop().time() - started_at
            assert elapsed < 1.0
            assert client.is_connected is False
            assert client.is_running() is False
            assert client.last_error is not None and "连接失败" in client.last_error
        finally:
            await client.stop()
            await server.stop()

    asyncio.run(scenario())
