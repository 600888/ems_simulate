import asyncio
from datetime import UTC, datetime, timedelta
import socket
import ssl
from types import SimpleNamespace

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from loguru import logger
import pytest

from src.device.core.message.message_formatter import MessageFormatter
from src.device.protocol.modbus_handler import ModbusServerHandler
from src.enums.modbus_def import ProtocolType
from src.proto.pyModbus.tls import (
    ModbusTlsConfigurationError,
    create_client_ssl_context,
    create_server_ssl_context,
)


def _create_ca():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Modbus Test CA")])
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
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
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


def test_one_way_tls_client_uses_only_ca_and_disables_hostname_check(tls_files):
    client = create_client_ssl_context(
        tls_mode="one_way",
        certificate_path=None,
        private_key_path=None,
        ca_certificate_path=tls_files["ca"],
    )
    server = create_server_ssl_context(
        tls_mode="one_way",
        certificate_path=tls_files["server_certificate"],
        private_key_path=tls_files["server_key"],
        ca_certificate_path=None,
    )

    assert client.minimum_version == ssl.TLSVersion.TLSv1_2
    assert client.maximum_version == ssl.TLSVersion.TLSv1_2
    assert client.check_hostname is False
    assert client.verify_mode == ssl.CERT_REQUIRED
    assert server.verify_mode == ssl.CERT_NONE


@pytest.mark.parametrize(
    ("tls_version", "expected_version"),
    [
        ("1.2", ssl.TLSVersion.TLSv1_2),
        ("1.3", ssl.TLSVersion.TLSv1_3),
    ],
)
def test_tls_version_pins_client_context_to_selected_version(tls_files, tls_version, expected_version):
    client = create_client_ssl_context(
        tls_mode="one_way",
        certificate_path=None,
        private_key_path=None,
        ca_certificate_path=tls_files["ca"],
        tls_version=tls_version,
    )

    assert client.minimum_version == expected_version
    assert client.maximum_version == expected_version


def test_tls_version_pins_server_context_to_selected_version(tls_files):
    server = create_server_ssl_context(
        tls_mode="one_way",
        certificate_path=tls_files["server_certificate"],
        private_key_path=tls_files["server_key"],
        ca_certificate_path=None,
        tls_version="1.3",
    )

    assert server.minimum_version == ssl.TLSVersion.TLSv1_3
    assert server.maximum_version == ssl.TLSVersion.TLSv1_3


def test_invalid_tls_version_is_rejected_by_client(tls_files):
    with pytest.raises(ModbusTlsConfigurationError, match="版本"):
        create_client_ssl_context(
            tls_mode="one_way",
            certificate_path=None,
            private_key_path=None,
            ca_certificate_path=tls_files["ca"],
            tls_version="1.1",
        )


def test_mutual_tls_requires_and_validates_peer_certificates(tls_files):
    client = create_client_ssl_context(
        tls_mode="mutual",
        certificate_path=tls_files["client_certificate"],
        private_key_path=tls_files["client_key"],
        ca_certificate_path=tls_files["ca"],
    )
    server = create_server_ssl_context(
        tls_mode="mutual",
        certificate_path=tls_files["server_certificate"],
        private_key_path=tls_files["server_key"],
        ca_certificate_path=tls_files["ca"],
    )

    assert client.check_hostname is False
    assert client.verify_mode == ssl.CERT_REQUIRED
    assert server.verify_mode == ssl.CERT_REQUIRED


def test_mutual_tls_rejects_missing_ca(tls_files):
    with pytest.raises(ModbusTlsConfigurationError, match="CA 证书"):
        create_client_ssl_context(
            tls_mode="mutual",
            certificate_path=tls_files["client_certificate"],
            private_key_path=tls_files["client_key"],
            ca_certificate_path=None,
        )


def test_one_way_tls_client_rejects_missing_ca():
    with pytest.raises(ModbusTlsConfigurationError, match="CA 证书"):
        create_client_ssl_context(
            tls_mode="one_way",
            certificate_path=None,
            private_key_path=None,
            ca_certificate_path=None,
        )


def test_invalid_tls_mode_is_rejected(tls_files):
    with pytest.raises(ModbusTlsConfigurationError, match="模式"):
        create_server_ssl_context(
            tls_mode="unknown",
            certificate_path=tls_files["server_certificate"],
            private_key_path=tls_files["server_key"],
            ca_certificate_path=tls_files["ca"],
        )


@pytest.mark.parametrize("tls_mode", [None, "one_way", "mutual"], ids=["tcp", "one_way", "mutual"])
def test_modbus_server_captures_request_and_response_once(tls_files, tls_mode):
    async def run_connection():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        client_ssl = None
        if tls_mode:
            client_ssl = create_client_ssl_context(
                tls_mode=tls_mode,
                certificate_path=tls_files["client_certificate"] if tls_mode == "mutual" else None,
                private_key_path=tls_files["client_key"] if tls_mode == "mutual" else None,
                ca_certificate_path=tls_files["ca"],
            )

        handler = ModbusServerHandler(logger)
        protocol_type = ProtocolType.ModbusTcpServer
        handler.initialize(
            {
                "channel_id": 1802,
                "protocol_type": protocol_type,
                "ip": "127.0.0.1",
                "port": port,
                "security": {
                    "tls_enabled": bool(tls_mode),
                    "tls_mode": tls_mode,
                    "certificate_path": tls_files["server_certificate"],
                    "private_key_path": tls_files["server_key"],
                    "ca_certificate_path": tls_files["ca"] if tls_mode == "mutual" else None,
                },
            }
        )
        request = bytes.fromhex("00 01 00 00 00 06 01 03 00 00 00 08")
        response = bytes.fromhex("00 01 00 00 00 13 01 03 10") + bytes(16)
        writer = None
        try:
            assert await handler.start()
            for _ in range(50):
                try:
                    reader, writer = await asyncio.open_connection("127.0.0.1", port, ssl=client_ssl)
                    break
                except ConnectionRefusedError:
                    await asyncio.sleep(0.01)
            else:
                raise AssertionError("Modbus server did not start listening")

            writer.write(request)
            await writer.drain()
            assert await asyncio.wait_for(reader.readexactly(len(response)), timeout=2) == response

            formatter = MessageFormatter(SimpleNamespace(protocol_handler=handler, protocol_type=protocol_type))
            messages = formatter.get_messages()
            assert [(message["direction"], message["raw_hex"]) for message in messages] == [
                ("RX", request.hex()),
                ("TX", response.hex()),
            ]
            assert "0x0000-0x0007" in messages[1]["description"]
            (connection,) = handler.get_current_connections()
            assert (connection["rx_messages"], connection["rx_bytes"]) == (1, len(request))
            assert (connection["tx_messages"], connection["tx_bytes"]) == (1, len(response))
        finally:
            if writer is not None:
                writer.close()
                await writer.wait_closed()
            await handler.stop()

    asyncio.run(run_connection())
