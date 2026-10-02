"""Explicit UA certificate validation, identities, and role permissions."""

import base64
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import ipaddress
import secrets
from urllib.parse import urlparse

from asyncua import ua
from asyncua.crypto.permission_rules import SimpleRoleRuleset
from asyncua.crypto.security_policies import SecurityPolicyBasic256Sha256
from asyncua.crypto.validator import CertificateValidator, CertificateValidatorOptions
from asyncua.server.user_managers import User, UserRole
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def certificate_info(der: bytes) -> dict:
    cert = x509.load_der_x509_certificate(der)
    return {
        "fingerprint": cert.fingerprint(hashes.SHA256()).hex(),
        "subject": cert.subject.rfc4514_string(),
        "issuer": cert.issuer.rfc4514_string(),
        "valid_from": cert.not_valid_before_utc.isoformat(),
        "valid_until": cert.not_valid_after_utc.isoformat(),
        "application_uris": cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value.get_values_for_type(x509.UniformResourceIdentifier),
    }


def generate_certificate(uri: str, host: str) -> tuple[bytes, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "EMS Simulate OPC UA")])
    try:
        hostname = x509.IPAddress(ipaddress.ip_address(host))
    except ValueError:
        hostname = x509.DNSName(host)
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName([hostname, x509.UniformResourceIdentifier(uri)]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=True,
                data_encipherment=True,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False
        )
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.DER), key.private_bytes(
        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )


def password_hash(password: str) -> str:
    if not 8 <= len(password) <= 1024:
        raise ValueError("密码须在 8 到 1024 字符之间")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310000)
    return f"{salt.hex()}:{digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    salt, digest = stored.split(":")
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 310000)
    return hmac.compare_digest(actual.hex(), digest)


class UaUsers:
    def __init__(self, config: dict, credentials: dict):
        self.config = config
        self.credentials = credentials

    def get_user(self, iserver, username=None, password=None, certificate=None):
        if username is None:
            if self.config.get("mode", "None") == "None":
                return User(role=UserRole.User)
            return User(role=UserRole.Anonymous) if self.config.get("allow_anonymous", False) else None
        for user in self.config.get("users", []):
            stored = self.credentials.get(f"user:{username}")
            if user["username"] == username and stored and password and check_password(password, stored):
                role = UserRole.User if user["role"] == "operator" else UserRole.Anonymous
                return User(role=role, name=username)
        return None


class UaPermissions(SimpleRoleRuleset):
    def __init__(self, config: dict):
        super().__init__()
        self.config = config

    def check_validity(self, user, action_type_id, body):
        if user.name:
            record = next((item for item in self.config.get("users", []) if item["username"] == user.name), None)
            if record is None:
                return False
            user = User(role=UserRole.User if record["role"] == "operator" else UserRole.Anonymous, name=user.name)
        if user.role == UserRole.Anonymous:
            # Viewers may browse/read/subscribe; model changes and writes remain denied.
            denied = {
                ua.ObjectIds.WriteRequest_Encoding_DefaultBinary,
                ua.ObjectIds.CallRequest_Encoding_DefaultBinary,
                ua.ObjectIds.AddNodesRequest_Encoding_DefaultBinary,
                ua.ObjectIds.DeleteNodesRequest_Encoding_DefaultBinary,
                ua.ObjectIds.AddReferencesRequest_Encoding_DefaultBinary,
                ua.ObjectIds.DeleteReferencesRequest_Encoding_DefaultBinary,
            }
            return action_type_id.Identifier not in denied
        return super().check_validity(user, action_type_id, body)


def validate_application_identity(config: dict, credentials: dict) -> None:
    if config.get("mode", "None") == "None":
        return
    if not config.get("certificate") or not credentials.get("private_key"):
        raise ValueError("安全连接需要应用证书和私钥")
    certificate = x509.load_der_x509_certificate(base64.b64decode(config["certificate"]))
    key = serialization.load_der_private_key(base64.b64decode(credentials["private_key"]), password=None)
    if certificate.public_key().public_numbers() != key.public_key().public_numbers():
        raise ValueError("应用证书与私钥不匹配")
    if (
        config.get("application_uri")
        not in certificate_info(base64.b64decode(config["certificate"]))["application_uris"]
    ):
        raise ValueError("Application URI 与应用证书不一致，请重新生成证书")
    if not certificate.not_valid_before_utc <= datetime.now(UTC) <= certificate.not_valid_after_utc:
        raise ValueError("应用证书尚未生效或已过期")


class PeerValidator:
    def __init__(self, config: dict, role: str, host: str | None = None, rejected=None):
        self.config = config
        self.host = host
        self.rejected = rejected
        options = CertificateValidatorOptions.EXT_VALIDATION | (
            CertificateValidatorOptions.PEER_SERVER if role == "server" else CertificateValidatorOptions.PEER_CLIENT
        )
        self.validator = CertificateValidator(options)

    async def __call__(self, cert, description):
        await self.validator(cert, description)
        fingerprint = cert.fingerprint(hashes.SHA256()).hex()
        if fingerprint not in self.config.get("trusted", []):
            if self.rejected:
                await self.rejected(cert.public_bytes(serialization.Encoding.DER))
            raise ua.UaStatusCodeError(ua.StatusCodes.BadCertificateUntrusted)
        if self.host:
            san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            try:
                valid = ipaddress.ip_address(self.host) in san.get_values_for_type(x509.IPAddress)
            except ValueError:
                valid = self.host.lower() in [name.lower() for name in san.get_values_for_type(x509.DNSName)]
            if not valid:
                raise ua.UaStatusCodeError(ua.StatusCodes.BadCertificateHostNameInvalid)


async def configure_client(client, config: dict, credentials: dict, rejected=None) -> None:
    validate_application_identity(config, credentials)
    client.application_uri = config.get("application_uri", "urn:ems-simulate:client")
    if config.get("mode", "None") == "None":
        if config.get("identity", "anonymous") != "anonymous":
            raise ValueError("用户名身份需要 SignAndEncrypt")
        return
    cert = base64.b64decode(config["certificate"])
    private_key = base64.b64decode(credentials["private_key"])
    await client.set_security(
        SecurityPolicyBasic256Sha256, cert, private_key, mode=ua.MessageSecurityMode[config["mode"]]
    )
    client.certificate_validator = PeerValidator(
        config, "server", urlparse(client.server_url.geturl()).hostname, rejected
    )
    if config.get("identity", "anonymous") == "username":
        client.set_user(config["username"])
        client.set_password(credentials["password"])


async def configure_server(server, config: dict, credentials: dict, rejected=None) -> None:
    validate_application_identity(config, credentials)
    await server.set_application_uri(config.get("application_uri", "urn:ems-simulate:server"))
    if config.get("mode", "None") == "None":
        server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
        server.set_identity_tokens([ua.AnonymousIdentityToken])
        return
    await server.load_certificate(base64.b64decode(config["certificate"]))
    await server.load_private_key(base64.b64decode(credentials["private_key"]))
    server.set_security_policy([ua.SecurityPolicyType[f"Basic256Sha256_{config['mode']}"]], UaPermissions(config))
    server.set_certificate_validator(PeerValidator(config, "client", rejected=rejected))
    tokens = [ua.UserNameIdentityToken]
    if config.get("allow_anonymous", False):
        tokens.append(ua.AnonymousIdentityToken)
    server.set_identity_tokens(tokens)
