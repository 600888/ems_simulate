import asyncio
from datetime import UTC, datetime, timedelta
import socket
import ssl

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import pytest

from src.proto.iec104.iec104client import IEC104Client
from src.proto.iec104.iec104server import IEC104Server
from src.proto.iec104.tls import (
    IEC104TlsConfigurationError,
    build_transport_security,
    load_one_way_tls_config,
)


def _create_ca():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "EMS Test CA")])
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
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return key, certificate


def _create_identity(common_name, ca_key, ca_certificate, eku):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_certificate.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([eku]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    return key, certificate


def _write_identity(
    directory,
    name,
    key,
    certificate,
    ca_certificate=None,
    *,
    tls_mode="mutual",
    client=None,
):
    certificate_path = directory / f"{name}.pem"
    private_key_path = directory / f"{name}.key"
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    private_key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    security = {
        "tls_enabled": True,
        "tls_mode": tls_mode,
        "certificate_path": str(certificate_path),
        "private_key_path": str(private_key_path),
    }
    if ca_certificate is not None:
        ca_path = directory / f"{name}-ca.pem"
        ca_path.write_bytes(ca_certificate.public_bytes(serialization.Encoding.PEM))
        security["ca_certificate_path"] = str(ca_path)
    if tls_mode == "one_way":
        return load_one_way_tls_config(security, client=bool(client))
    return build_transport_security(security)


def _available_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_disabled_tls_does_not_require_certificate_files():
    assert build_transport_security({"tls_enabled": False}) is None


def test_mutual_tls_requires_ca_certificate(tmp_path):
    certificate = tmp_path / "identity.pem"
    private_key = tmp_path / "identity.key"
    certificate.write_text("invalid")
    private_key.write_text("invalid")
    with pytest.raises(IEC104TlsConfigurationError, match="CA 证书"):
        build_transport_security(
            {
                "tls_enabled": True,
                "tls_mode": "mutual",
                "certificate_path": str(certificate),
                "private_key_path": str(private_key),
            }
        )


def test_one_way_client_requires_only_ca_certificate(tmp_path):
    _, ca_certificate = _create_ca()
    ca_path = tmp_path / "one-way-ca.pem"
    ca_path.write_bytes(ca_certificate.public_bytes(serialization.Encoding.PEM))

    tls_config = load_one_way_tls_config(
        {
            "tls_enabled": True,
            "tls_mode": "one_way",
            "ca_certificate_path": str(ca_path),
        },
        client=True,
    )

    assert tls_config is not None
    context = tls_config.create_client_context()
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is False


def test_invalid_tls_mode_is_rejected(tmp_path):
    certificate = tmp_path / "identity.pem"
    private_key = tmp_path / "identity.key"
    certificate.write_text("invalid")
    private_key.write_text("invalid")
    with pytest.raises(IEC104TlsConfigurationError, match="模式"):
        build_transport_security(
            {
                "tls_enabled": True,
                "tls_mode": "unknown",
                "certificate_path": str(certificate),
                "private_key_path": str(private_key),
            }
        )


def test_iec104_client_and_server_connect_over_one_way_tls(tmp_path):
    server_ca_key, server_ca = _create_ca()
    server_key, server_certificate = _create_identity(
        "ems-server",
        server_ca_key,
        server_ca,
        ExtendedKeyUsageOID.SERVER_AUTH,
    )
    client_ca_key, client_ca = _create_ca()
    client_key, client_certificate = _create_identity(
        "ems-client",
        client_ca_key,
        client_ca,
        ExtendedKeyUsageOID.CLIENT_AUTH,
    )
    server_tls = _write_identity(
        tmp_path,
        "one-way-server",
        server_key,
        server_certificate,
        tls_mode="one_way",
        client=False,
    )
    client_tls = _write_identity(
        tmp_path,
        "one-way-client",
        client_key,
        client_certificate,
        server_ca,
        tls_mode="one_way",
        client=True,
    )

    port = _available_port()
    server = IEC104Server(ip="127.0.0.1", port=port, one_way_tls_config=server_tls)
    server.get_station(common_address=1)
    client = IEC104Client(ip="127.0.0.1", port=port, one_way_tls_config=client_tls)
    client.get_station(common_address=1)
    try:
        server.start()
        assert asyncio.run(client.connect(timeout=3)) is True
        assert client.is_connected is True

        client.disconnect()
        server.stop()

        server.start()
        assert asyncio.run(client.connect(timeout=3)) is True
        assert client.is_connected is True
    finally:
        client.disconnect()
        server.stop()


def test_iec104_client_and_server_connect_over_mutual_tls(tmp_path):
    ca_key, ca_certificate = _create_ca()
    server_key, server_certificate = _create_identity(
        "ems-server",
        ca_key,
        ca_certificate,
        ExtendedKeyUsageOID.SERVER_AUTH,
    )
    client_key, client_certificate = _create_identity(
        "ems-client",
        ca_key,
        ca_certificate,
        ExtendedKeyUsageOID.CLIENT_AUTH,
    )
    server_tls = _write_identity(tmp_path, "server", server_key, server_certificate, ca_certificate)
    client_tls = _write_identity(
        tmp_path,
        "client",
        client_key,
        client_certificate,
        ca_certificate,
    )

    port = _available_port()
    server = IEC104Server(ip="127.0.0.1", port=port, transport_security=server_tls)
    server.get_station(common_address=1)
    client = IEC104Client(ip="127.0.0.1", port=port, transport_security=client_tls)
    client.get_station(common_address=1)
    try:
        server.start()
        assert asyncio.run(client.connect(timeout=3)) is True
        assert client.is_connected is True

        client.disconnect()
        server.stop()

        server.start()
        assert asyncio.run(client.connect(timeout=3)) is True
        assert client.is_connected is True
    finally:
        client.disconnect()
        server.stop()


def test_iec104_rejects_client_signed_by_untrusted_ca(tmp_path):
    trusted_ca_key, trusted_ca = _create_ca()
    server_key, server_certificate = _create_identity(
        "ems-server",
        trusted_ca_key,
        trusted_ca,
        ExtendedKeyUsageOID.SERVER_AUTH,
    )
    untrusted_ca_key, untrusted_ca = _create_ca()
    client_key, client_certificate = _create_identity(
        "untrusted-client",
        untrusted_ca_key,
        untrusted_ca,
        ExtendedKeyUsageOID.CLIENT_AUTH,
    )
    server_tls = _write_identity(tmp_path, "server", server_key, server_certificate, trusted_ca)
    # The client trusts the server CA, but presents an identity issued by another CA.
    client_tls = _write_identity(
        tmp_path,
        "client",
        client_key,
        client_certificate,
        trusted_ca,
    )

    port = _available_port()
    server = IEC104Server(ip="127.0.0.1", port=port, transport_security=server_tls)
    server.get_station(common_address=1)
    client = IEC104Client(ip="127.0.0.1", port=port, transport_security=client_tls)
    client.get_station(common_address=1)
    try:
        server.start()
        assert asyncio.run(client.connect(timeout=1)) is False
        assert client.is_connected is False
    finally:
        client.disconnect()
        server.stop()


def test_iec104_mutual_tls_does_not_validate_server_hostname(tmp_path):
    ca_key, ca_certificate = _create_ca()
    server_key, server_certificate = _create_identity(
        "ems-server",
        ca_key,
        ca_certificate,
        ExtendedKeyUsageOID.SERVER_AUTH,
    )
    client_key, client_certificate = _create_identity(
        "ems-client",
        ca_key,
        ca_certificate,
        ExtendedKeyUsageOID.CLIENT_AUTH,
    )
    server_tls = _write_identity(tmp_path, "server", server_key, server_certificate, ca_certificate)
    client_tls = _write_identity(
        tmp_path,
        "client",
        client_key,
        client_certificate,
        ca_certificate,
    )

    port = _available_port()
    server = IEC104Server(ip="127.0.0.1", port=port, transport_security=server_tls)
    server.get_station(common_address=1)
    client = IEC104Client(ip="127.0.0.1", port=port, transport_security=client_tls)
    client.get_station(common_address=1)
    try:
        server.start()
        assert asyncio.run(client.connect(timeout=3)) is True
        assert client.is_connected is True
    finally:
        client.disconnect()
        server.stop()
