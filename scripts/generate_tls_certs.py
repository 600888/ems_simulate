"""Generate development certificates for one-way TLS and mutual TLS."""

from __future__ import annotations

import argparse
from contextlib import suppress
from datetime import UTC, datetime, timedelta
import ipaddress
from pathlib import Path
import stat

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

KEY_SIZE = 3072
LEAF_VALID_DAYS = 825
CA_VALID_DAYS = 3650


def new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE)


def subject(common_name: str, organization: str) -> x509.Name:
    return x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )


def write_key(path: Path, key: rsa.RSAPrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    with suppress(OSError):
        # Windows ACLs do not always map to POSIX permission bits.
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def write_cert(path: Path, cert: x509.Certificate) -> None:
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def san_extension(dns_names: list[str], ip_addresses: list[str]) -> x509.SubjectAlternativeName:
    names: list[x509.GeneralName] = [x509.DNSName(name) for name in dns_names]
    names.extend(x509.IPAddress(ipaddress.ip_address(value)) for value in ip_addresses)
    return x509.SubjectAlternativeName(names)


def create_ca(common_name: str) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = new_key()
    name = subject(common_name, "EMS Simulate Development")
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=CA_VALID_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return key, cert


def create_leaf(
    common_name: str,
    issuer_cert: x509.Certificate | None,
    issuer_key: rsa.RSAPrivateKey | None,
    usage: x509.ObjectIdentifier,
    dns_names: list[str] | None = None,
    ip_addresses: list[str] | None = None,
) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = new_key()
    leaf_subject = subject(common_name, "EMS Simulate Development")
    signing_cert = issuer_cert
    signing_key = issuer_key or key
    issuer_name = signing_cert.subject if signing_cert else leaf_subject
    now = datetime.now(UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(leaf_subject)
        .issuer_name(issuer_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=LEAF_VALID_DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([usage]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
    )
    if signing_cert:
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(signing_key.public_key()),
            critical=False,
        )
    if dns_names or ip_addresses:
        builder = builder.add_extension(san_extension(dns_names or [], ip_addresses or []), critical=False)
    return key, builder.sign(signing_key, hashes.SHA256())


def ensure_empty_output(path: Path, force: bool) -> None:
    expected = [
        path / "one-way" / "server.key.pem",
        path / "one-way" / "server.crt.pem",
        path / "mutual" / "ca.key.pem",
        path / "mutual" / "ca.crt.pem",
        path / "mutual" / "server.key.pem",
        path / "mutual" / "server.crt.pem",
        path / "mutual" / "client.key.pem",
        path / "mutual" / "client.crt.pem",
    ]
    existing = [file for file in expected if file.exists()]
    if existing and not force:
        names = ", ".join(str(file) for file in existing)
        raise SystemExit(f"Refusing to overwrite existing files: {names}. Use --force to replace them.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("certs"), help="Output directory (default: certs)")
    parser.add_argument("--dns", action="append", default=[], help="Additional server DNS SAN; repeat as needed")
    parser.add_argument("--ip", action="append", default=[], help="Additional server IP SAN; repeat as needed")
    parser.add_argument("--force", action="store_true", help="Replace previously generated files")
    args = parser.parse_args()

    dns_names = list(dict.fromkeys(["localhost", *args.dns]))
    ip_addresses = list(dict.fromkeys(["127.0.0.1", "::1", *args.ip]))
    output = args.output.resolve()
    ensure_empty_output(output, args.force)

    one_way = output / "one-way"
    mutual = output / "mutual"
    one_way.mkdir(parents=True, exist_ok=True)
    mutual.mkdir(parents=True, exist_ok=True)

    one_key, one_cert = create_leaf(
        "localhost",
        issuer_cert=None,
        issuer_key=None,
        usage=ExtendedKeyUsageOID.SERVER_AUTH,
        dns_names=dns_names,
        ip_addresses=ip_addresses,
    )
    write_key(one_way / "server.key.pem", one_key)
    write_cert(one_way / "server.crt.pem", one_cert)

    ca_key, ca_cert = create_ca("EMS Simulate Development Root CA")
    write_key(mutual / "ca.key.pem", ca_key)
    write_cert(mutual / "ca.crt.pem", ca_cert)

    server_key, server_cert = create_leaf(
        "localhost",
        issuer_cert=ca_cert,
        issuer_key=ca_key,
        usage=ExtendedKeyUsageOID.SERVER_AUTH,
        dns_names=dns_names,
        ip_addresses=ip_addresses,
    )
    write_key(mutual / "server.key.pem", server_key)
    write_cert(mutual / "server.crt.pem", server_cert)

    client_key, client_cert = create_leaf(
        "ems-simulate-client",
        issuer_cert=ca_cert,
        issuer_key=ca_key,
        usage=ExtendedKeyUsageOID.CLIENT_AUTH,
    )
    write_key(mutual / "client.key.pem", client_key)
    write_cert(mutual / "client.crt.pem", client_cert)

    print(f"Generated TLS files in {output}")
    print(f"Server SAN DNS: {', '.join(dns_names)}")
    print(f"Server SAN IP: {', '.join(ip_addresses)}")


if __name__ == "__main__":
    main()
