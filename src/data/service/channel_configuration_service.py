"""Persistence service for protocol runtime and TLS configuration."""

from pathlib import Path
import shutil
from typing import Any

from src.config.storage import get_storage_path
from src.data.controller.db import local_session
from src.data.model.channel_configuration import ChannelProtocolParams, ChannelSecurityConfig
from src.device.protocol.runtime_config import get_protocol_param_defaults, normalize_protocol_params

TLS_MODE_ONE_WAY = "one_way"
TLS_MODE_MUTUAL = "mutual"


def normalize_tls_mode(value: Any) -> str:
    """Normalize persisted TLS modes, including the removed legacy basic mode."""
    mode = str(value or TLS_MODE_ONE_WAY)
    if mode == "basic":
        return TLS_MODE_ONE_WAY
    if mode in {TLS_MODE_ONE_WAY, TLS_MODE_MUTUAL}:
        return mode
    return TLS_MODE_ONE_WAY


class ChannelConfigurationService:
    @classmethod
    def get_protocol_params(cls, channel_id: int, protocol_type: int, conn_type: int) -> dict[str, Any]:
        with local_session() as session, session.begin():
            record = session.get(ChannelProtocolParams, channel_id)
            if not record or record.protocol_type != protocol_type or record.conn_type != conn_type:
                values = get_protocol_param_defaults(protocol_type, conn_type)
                if record is None:
                    record = ChannelProtocolParams(
                        channel_id=channel_id,
                        protocol_type=protocol_type,
                        conn_type=conn_type,
                        schema_version=1,
                        params_json=values,
                    )
                    session.add(record)
                else:
                    record.protocol_type = protocol_type
                    record.conn_type = conn_type
                    record.schema_version = 1
                    record.params_json = values
                return {"schema_version": 1, "values": values}
            values = normalize_protocol_params(protocol_type, conn_type, record.params_json)
            # Persist newly introduced defaults so existing databases are
            # upgraded when their channel configuration is first read.
            if record.params_json != values:
                record.params_json = values
            return {"schema_version": record.schema_version, "values": values}

    @classmethod
    def save_protocol_params(
        cls,
        channel_id: int,
        protocol_type: int,
        conn_type: int,
        values: dict[str, Any] | None,
        schema_version: int = 1,
    ) -> dict[str, Any]:
        normalized = normalize_protocol_params(protocol_type, conn_type, values)
        with local_session() as session, session.begin():
            record = session.get(ChannelProtocolParams, channel_id)
            if record is None:
                record = ChannelProtocolParams(
                    channel_id=channel_id,
                    protocol_type=protocol_type,
                    conn_type=conn_type,
                    schema_version=schema_version,
                    params_json=normalized,
                )
                session.add(record)
            else:
                record.protocol_type = protocol_type
                record.conn_type = conn_type
                record.schema_version = schema_version
                record.params_json = normalized
        return {"schema_version": schema_version, "values": normalized}

    @classmethod
    def get_security_config(cls, channel_id: int) -> dict[str, Any]:
        with local_session() as session:
            record = session.get(ChannelSecurityConfig, channel_id)
            if not record:
                return {
                    "tls_enabled": False,
                    "tls_mode": TLS_MODE_ONE_WAY,
                    "certificate_configured": False,
                    "certificate_filename": None,
                    "private_key_configured": False,
                    "private_key_filename": None,
                    "ca_certificate_configured": False,
                    "ca_certificate_filename": None,
                }
            return {
                "tls_enabled": record.tls_enabled,
                "tls_mode": normalize_tls_mode(record.tls_mode),
                "certificate_configured": bool(record.certificate_path),
                "certificate_filename": record.certificate_filename,
                "private_key_configured": bool(record.private_key_path),
                "private_key_filename": record.private_key_filename,
                "ca_certificate_configured": bool(record.ca_certificate_path),
                "ca_certificate_filename": record.ca_certificate_filename,
            }

    @classmethod
    def get_runtime_security(cls, channel_id: int) -> dict[str, Any]:
        with local_session() as session:
            record = session.get(ChannelSecurityConfig, channel_id)
            if not record:
                return {
                    "tls_enabled": False,
                    "tls_mode": TLS_MODE_ONE_WAY,
                    "certificate_path": None,
                    "private_key_path": None,
                    "ca_certificate_path": None,
                }
            return {
                "tls_enabled": record.tls_enabled,
                "tls_mode": normalize_tls_mode(record.tls_mode),
                "certificate_path": record.certificate_path,
                "private_key_path": record.private_key_path,
                "ca_certificate_path": record.ca_certificate_path,
            }

    @classmethod
    def save_security_config(
        cls,
        channel_id: int,
        *,
        tls_enabled: bool,
        certificate_path: str | None,
        certificate_filename: str | None,
        private_key_path: str | None,
        private_key_filename: str | None,
        ca_certificate_path: str | None = None,
        ca_certificate_filename: str | None = None,
        tls_mode: str = TLS_MODE_ONE_WAY,
    ) -> None:
        with local_session() as session, session.begin():
            record = session.get(ChannelSecurityConfig, channel_id)
            if record is None:
                record = ChannelSecurityConfig(channel_id=channel_id)
                session.add(record)
            record.tls_enabled = tls_enabled
            record.tls_mode = normalize_tls_mode(tls_mode)
            record.certificate_path = certificate_path
            record.certificate_filename = certificate_filename
            record.private_key_path = private_key_path
            record.private_key_filename = private_key_filename
            record.ca_certificate_path = ca_certificate_path
            record.ca_certificate_filename = ca_certificate_filename

    @classmethod
    def clone_for_channel(
        cls,
        source_channel_id: int,
        target_channel_id: int,
        protocol_type: int,
        conn_type: int,
    ) -> None:
        """复制协议参数、TLS 数据库配置及证书文件到新通道。"""
        protocol = cls.get_protocol_params(source_channel_id, protocol_type, conn_type)
        cls.save_protocol_params(
            target_channel_id,
            protocol_type,
            conn_type,
            protocol["values"],
            schema_version=protocol["schema_version"],
        )

        public_security = cls.get_security_config(source_channel_id)
        runtime_security = cls.get_runtime_security(source_channel_id)
        security_root = (Path(get_storage_path("data_directory")) / "security").resolve(strict=False)
        target_dir = (security_root / str(target_channel_id)).resolve(strict=False)
        if target_dir.parent != security_root:
            raise ValueError("TLS 文件目标目录无效")

        def copy_security_file(source_path: str | None, target_name: str) -> str | None:
            if not source_path:
                return None
            source = Path(source_path)
            if not source.is_file():
                raise FileNotFoundError(f"TLS 配置文件不存在: {source.name}")
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / target_name
            shutil.copy2(source, target)
            target.chmod(0o600)
            return str(target)

        certificate_path = copy_security_file(runtime_security.get("certificate_path"), "certificate.pem")
        private_key_path = copy_security_file(runtime_security.get("private_key_path"), "private_key.pem")
        ca_certificate_path = copy_security_file(runtime_security.get("ca_certificate_path"), "ca_certificate.pem")
        cls.save_security_config(
            target_channel_id,
            tls_enabled=bool(runtime_security.get("tls_enabled")),
            tls_mode=normalize_tls_mode(runtime_security.get("tls_mode")),
            certificate_path=certificate_path,
            certificate_filename=public_security.get("certificate_filename"),
            private_key_path=private_key_path,
            private_key_filename=public_security.get("private_key_filename"),
            ca_certificate_path=ca_certificate_path,
            ca_certificate_filename=public_security.get("ca_certificate_filename"),
        )

    @classmethod
    def delete_for_channel(cls, channel_id: int) -> None:
        with local_session() as session, session.begin():
            session.query(ChannelProtocolParams).where(ChannelProtocolParams.channel_id == channel_id).delete()
            session.query(ChannelSecurityConfig).where(ChannelSecurityConfig.channel_id == channel_id).delete()

        security_root = (Path(get_storage_path("data_directory")) / "security").resolve(strict=False)
        channel_dir = (security_root / str(channel_id)).resolve(strict=False)
        if channel_dir.parent == security_root and channel_dir.name == str(channel_id) and channel_dir.is_dir():
            shutil.rmtree(channel_dir, ignore_errors=True)
