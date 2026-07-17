"""Persistence service for protocol runtime and TLS configuration."""

from pathlib import Path
import shutil
from typing import Any

from src.config.storage import get_storage_path
from src.data.controller.db import local_session
from src.data.model.channel_configuration import ChannelProtocolParams, ChannelSecurityConfig
from src.device.protocol.runtime_config import get_protocol_param_defaults, normalize_protocol_params


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
                    "tls_mode": "mutual",
                    "certificate_configured": False,
                    "certificate_filename": None,
                    "private_key_configured": False,
                    "private_key_filename": None,
                    "ca_certificate_configured": False,
                    "ca_certificate_filename": None,
                }
            return {
                "tls_enabled": record.tls_enabled,
                "tls_mode": record.tls_mode or "mutual",
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
                    "tls_mode": "mutual",
                    "certificate_path": None,
                    "private_key_path": None,
                    "ca_certificate_path": None,
                }
            return {
                "tls_enabled": record.tls_enabled,
                "tls_mode": record.tls_mode or "mutual",
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
        tls_mode: str = "mutual",
    ) -> None:
        with local_session() as session, session.begin():
            record = session.get(ChannelSecurityConfig, channel_id)
            if record is None:
                record = ChannelSecurityConfig(channel_id=channel_id)
                session.add(record)
            record.tls_enabled = tls_enabled
            record.tls_mode = tls_mode
            record.certificate_path = certificate_path
            record.certificate_filename = certificate_filename
            record.private_key_path = private_key_path
            record.private_key_filename = private_key_filename
            record.ca_certificate_path = ca_certificate_path
            record.ca_certificate_filename = ca_certificate_filename

    @classmethod
    def delete_for_channel(cls, channel_id: int) -> None:
        with local_session() as session, session.begin():
            session.query(ChannelProtocolParams).where(ChannelProtocolParams.channel_id == channel_id).delete()
            session.query(ChannelSecurityConfig).where(ChannelSecurityConfig.channel_id == channel_id).delete()

        security_root = (Path(get_storage_path("data_directory")) / "security").resolve(strict=False)
        channel_dir = (security_root / str(channel_id)).resolve(strict=False)
        if channel_dir.parent == security_root and channel_dir.name == str(channel_id) and channel_dir.is_dir():
            shutil.rmtree(channel_dir, ignore_errors=True)
