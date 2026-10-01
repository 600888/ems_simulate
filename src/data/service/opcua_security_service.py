"""Certificate approval and protected credentials; public output excludes secrets."""

import base64
from pathlib import Path

from sqlalchemy import select

from src.config.storage import get_storage_path
from src.data.controller.db import local_session
from src.data.model.opcua_secret import OpcUaSecret
from src.data.service.opcua_feature_service import OpcUaFeatureService
from src.proto.opcua.core.security import certificate_info, generate_certificate, password_hash
from src.proto.opcua.core.vault import protect


class OpcUaSecurityService:
    @staticmethod
    def _directory():
        return Path(get_storage_path("data_directory")) / "opcua"

    @staticmethod
    def secrets(channel_id: int) -> dict:
        with local_session() as session:
            return {
                row.name: protect(row.ciphertext, OpcUaSecurityService._directory(), decrypt=True)
                for row in session.scalars(select(OpcUaSecret).where(OpcUaSecret.channel_id == channel_id))
            }

    @staticmethod
    def save_secret(channel_id: int, name: str, value: str) -> None:
        encrypted = protect(value, OpcUaSecurityService._directory())
        with local_session() as session, session.begin():
            row = session.get(OpcUaSecret, (channel_id, name))
            if row is None:
                session.add(OpcUaSecret(channel_id=channel_id, name=name, ciphertext=encrypted))
            else:
                row.ciphertext = encrypted

    @staticmethod
    def generate(channel_id: int, application_uri: str, host: str) -> dict:
        cert, key = generate_certificate(application_uri, host)
        OpcUaSecurityService.save_secret(channel_id, "private_key", base64.b64encode(key).decode())
        config = OpcUaFeatureService.load(channel_id).get("security", {})
        config.update(application_uri=application_uri, certificate=base64.b64encode(cert).decode())
        OpcUaFeatureService.save(channel_id, "security", config)
        return certificate_info(cert)

    @staticmethod
    def register_peer(channel_id: int, der: bytes) -> dict:
        info = certificate_info(der)
        certificates = OpcUaFeatureService.load(channel_id).get("certificates", {}).get("peers", [])
        if not any(item["fingerprint"] == info["fingerprint"] for item in certificates):
            certificates = certificates[-99:] + [{**info, "certificate": base64.b64encode(der).decode()}]
            OpcUaFeatureService.save(channel_id, "certificates", {"peers": certificates})
        return info

    @staticmethod
    def trust(channel_id: int, fingerprint: str, trusted: bool) -> None:
        records = OpcUaFeatureService.load(channel_id)
        peers = records.get("certificates", {}).get("peers", [])
        if trusted and not any(item["fingerprint"] == fingerprint for item in peers):
            raise ValueError("证书不存在，请先发现 Endpoint 或上传对端证书")
        config = records.get("security", {})
        fingerprints = set(config.get("trusted", []))
        if trusted:
            fingerprints.add(fingerprint)
        else:
            fingerprints.discard(fingerprint)
        config["trusted"] = sorted(fingerprints)
        OpcUaFeatureService.save(channel_id, "security", config)

    @staticmethod
    def user(channel_id: int, username: str, role: str, password: str | None) -> None:
        if role not in {"viewer", "operator"} or not 1 <= len(username) <= 64:
            raise ValueError("用户名或角色无效")
        config = OpcUaFeatureService.load(channel_id).get("security", {})
        users = [user for user in config.get("users", []) if user["username"] != username]
        if len(users) >= 100:
            raise ValueError("用户数量超过上限")
        if password:
            OpcUaSecurityService.save_secret(channel_id, f"user:{username}", password_hash(password))
            users.append({"username": username, "role": role})
        else:
            with local_session() as session, session.begin():
                row = session.get(OpcUaSecret, (channel_id, f"user:{username}"))
                if row:
                    session.delete(row)
        config["users"] = users
        OpcUaFeatureService.save(channel_id, "security", config)
