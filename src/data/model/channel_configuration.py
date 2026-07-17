"""Per-channel protocol runtime and TLS configuration."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.data.model.base import Base


class ChannelProtocolParams(Base):
    __tablename__ = "channel_protocol_params"

    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channel.id"), primary_key=True)
    protocol_type: Mapped[int] = mapped_column(Integer, nullable=False)
    conn_type: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    params_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ChannelSecurityConfig(Base):
    __tablename__ = "channel_security_config"

    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channel.id"), primary_key=True)
    tls_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    tls_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="mutual", server_default="mutual")
    certificate_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    certificate_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    private_key_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    private_key_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ca_certificate_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ca_certificate_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
