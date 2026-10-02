"""Atomic device-form endpoint and UA SecureChannel configuration."""

import base64
from urllib.parse import urlparse

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from sqlalchemy import select

from src.data.controller.db import local_session
from src.data.model.channel import Channel
from src.data.model.channel_configuration import ChannelProtocolParams
from src.data.model.opcua_config import OpcUaConfig
from src.data.model.opcua_feature import OpcUaFeature
from src.data.model.opcua_node import OpcUaNode
from src.data.model.opcua_secret import OpcUaSecret
from src.data.service.opcua_config_service import OpcUaConfigService
from src.data.service.opcua_feature_service import OpcUaFeatureService
from src.data.service.opcua_security_service import OpcUaSecurityService
from src.proto.opcua.core.feature_config import SecurityConfig
from src.proto.opcua.core.security import certificate_info, generate_certificate, validate_application_identity
from src.proto.opcua.core.transport import loopback_endpoint, make_endpoint_url, validate_endpoint
from src.proto.opcua.core.vault import protect


def _certificate(encoded: str) -> bytes:
    try:
        content = base64.b64decode(encoded, validate=True)
        cert = (
            x509.load_pem_x509_certificate(content)
            if b"-----BEGIN" in content
            else x509.load_der_x509_certificate(content)
        )
        return cert.public_bytes(serialization.Encoding.DER)
    except (ValueError, TypeError) as exc:
        raise ValueError("无法解析 OPC UA 应用证书或对端证书") from exc


def _private_key(encoded: str) -> bytes:
    try:
        content = base64.b64decode(encoded, validate=True)
        key = (
            serialization.load_pem_private_key(content, password=None)
            if b"-----BEGIN" in content
            else serialization.load_der_private_key(content, password=None)
        )
        return key.private_bytes(
            serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    except (ValueError, TypeError) as exc:
        raise ValueError("无法解析 OPC UA 私钥，请上传未加密的 PEM 或 DER 私钥") from exc


class OpcUaDeviceConfigurationService:
    @staticmethod
    def public(channel_id: int) -> dict:
        endpoint = OpcUaConfigService.get(channel_id)
        security = OpcUaFeatureService.load(channel_id).get("security", {})
        with local_session() as session:
            secret_names = set(session.scalars(select(OpcUaSecret.name).where(OpcUaSecret.channel_id == channel_id)))
        return {
            "endpoint_path": (urlparse(endpoint["endpoint_url"]).path or "/")
            if endpoint["role"] == "client"
            else endpoint["endpoint_path"],
            "namespace_uri": endpoint["namespace_uri"],
            **{
                key: security.get(key, default)
                for key, default in (
                    ("mode", "None"),
                    ("application_uri", "urn:ems-simulate:application"),
                    ("advertised_host", None),
                    ("identity", "anonymous"),
                    ("username", ""),
                    ("allow_anonymous", False),
                )
            },
            "policy": "Basic256Sha256",
            "certificate_configured": bool(security.get("certificate")),
            "private_key_configured": "private_key" in secret_names,
            "password_configured": "password" in secret_names,
            "trusted_count": len(security.get("trusted", [])),
        }

    @staticmethod
    def prepare(body, host: str, port: int, conn_type: int, channel_id: int | None = None) -> dict:
        path = body.endpoint_path.strip()
        if not path.startswith("/") or any(c in path for c in ("?", "#", "\\")):
            raise ValueError("Endpoint 路径必须以 / 开头，且不含查询参数或片段")
        saved = OpcUaFeatureService.load(channel_id).get("security", {}) if channel_id else {}
        credentials = OpcUaSecurityService.secrets(channel_id) if channel_id else {}
        security = {
            **saved,
            **body.model_dump(
                include={
                    "mode",
                    "application_uri",
                    "advertised_host",
                    "identity",
                    "username",
                    "allow_anonymous",
                }
            ),
        }
        security["advertised_host"] = security.get("advertised_host") or None
        if conn_type == 2 and security["identity"] != "anonymous":
            raise ValueError("用户名身份参数仅适用于 OPC UA 客户端")
        secrets = {}
        if body.generate_certificate:
            cert, key = generate_certificate(body.application_uri, body.advertised_host or host)
            security["certificate"] = base64.b64encode(cert).decode()
            secrets["private_key"] = base64.b64encode(key).decode()
        if body.certificate:
            security["certificate"] = base64.b64encode(_certificate(body.certificate)).decode()
        if body.private_key:
            secrets["private_key"] = base64.b64encode(_private_key(body.private_key.get_secret_value())).decode()
        if body.password and body.password.get_secret_value():
            password = body.password.get_secret_value()
            if not 1 <= len(password) <= 1024:
                raise ValueError("密码长度必须在 1 到 1024 个字符之间")
            secrets["password"] = password
        peer = _certificate(body.peer_certificate) if body.peer_certificate else None
        if peer:
            try:
                fingerprint = certificate_info(peer)["fingerprint"]
            except x509.ExtensionNotFound as exc:
                raise ValueError("OPC UA 对端证书必须包含 Subject Alternative Name 和 Application URI") from exc
            security["trusted"] = sorted(set(security.get("trusted", [])) | {fingerprint})
        security = SecurityConfig.model_validate(security).model_dump()
        try:
            validate_application_identity(security, {**credentials, **secrets})
        except x509.ExtensionNotFound as exc:
            raise ValueError("OPC UA 应用证书必须包含 Subject Alternative Name 和 Application URI") from exc
        if security["identity"] == "username" and not (secrets.get("password") or credentials.get("password")):
            raise ValueError("用户名身份需要填写密码")
        endpoint = make_endpoint_url(host, port, path)
        validator = loopback_endpoint if security["mode"] == "None" else validate_endpoint
        validator(endpoint)
        if conn_type == 2 and security.get("advertised_host"):
            validator(make_endpoint_url(security["advertised_host"], port, path))
        namespace = body.namespace_uri.strip()
        if channel_id and conn_type == 2:
            with local_session() as session:
                record = session.get(OpcUaConfig, channel_id)
                old_uri = (record.namespace_uri if record else None) or f"urn:ems-simulate:channel:{channel_id}"
                new_uri = namespace or f"urn:ems-simulate:channel:{channel_id}"
                if (
                    new_uri != old_uri
                    and session.scalar(select(OpcUaNode.id).where(OpcUaNode.channel_id == channel_id).limit(1))
                    is not None
                ):
                    raise ValueError("已有节点定义时不能更改命名空间 URI")
        return {
            "endpoint_url": endpoint,
            "endpoint_path": path,
            "namespace_uri": namespace,
            "security": security,
            "secrets": secrets,
            "peer": peer,
        }

    @staticmethod
    def persist(session, channel_id: int, conn_type: int, prepared: dict) -> None:
        endpoint = session.get(OpcUaConfig, channel_id)
        if endpoint is None:
            endpoint = OpcUaConfig(channel_id=channel_id)
            session.add(endpoint)
        endpoint.endpoint_path = prepared["endpoint_path"]
        endpoint.endpoint_url = prepared["endpoint_url"] if conn_type == 1 else None
        endpoint.namespace_uri = prepared["namespace_uri"] or f"urn:ems-simulate:channel:{channel_id}"
        security = session.get(OpcUaFeature, (channel_id, "security"))
        if security is None:
            session.add(OpcUaFeature(channel_id=channel_id, name="security", config=prepared["security"]))
        else:
            security.config = prepared["security"]
        for name, value in prepared["secrets"].items():
            ciphertext = protect(value, OpcUaSecurityService._directory())
            secret = session.get(OpcUaSecret, (channel_id, name))
            if secret is None:
                session.add(OpcUaSecret(channel_id=channel_id, name=name, ciphertext=ciphertext))
            else:
                secret.ciphertext = ciphertext
        if prepared["peer"]:
            peer = {**certificate_info(prepared["peer"]), "certificate": base64.b64encode(prepared["peer"]).decode()}
            row = session.get(OpcUaFeature, (channel_id, "certificates"))
            peers = row.config.get("peers", []) if row else []
            if not any(item["fingerprint"] == peer["fingerprint"] for item in peers):
                peers = peers[-99:] + [peer]
            if row:
                row.config = {"peers": peers}
            else:
                session.add(OpcUaFeature(channel_id=channel_id, name="certificates", config={"peers": peers}))

    @staticmethod
    def update(
        channel_id: int, conn_type: int, prepared: dict, channel_updates: dict, params: dict | None, schema_version: int
    ) -> None:
        with local_session() as session, session.begin():
            channel = session.get(Channel, channel_id)
            for name, value in channel_updates.items():
                setattr(channel, name, value)
            OpcUaDeviceConfigurationService.persist(session, channel_id, conn_type, prepared)
            if params is not None:
                record = session.get(ChannelProtocolParams, channel_id)
                if record is None:
                    record = ChannelProtocolParams(channel_id=channel_id)
                    session.add(record)
                record.protocol_type, record.conn_type = 7, conn_type
                record.schema_version, record.params_json = schema_version, params
