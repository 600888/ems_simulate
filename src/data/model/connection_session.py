"""Persisted server-side client connection history."""

from datetime import UTC
import json
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.data.model.base import Base


class ConnectionSession(Base):
    __tablename__ = "connection_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channel.id", ondelete="CASCADE"), nullable=False)
    protocol_type: Mapped[str] = mapped_column(String(32), nullable=False)
    server_instance_id: Mapped[str] = mapped_column(String(36), nullable=False)
    remote_ip: Mapped[str | None] = mapped_column(String(45))
    remote_port: Mapped[int | None] = mapped_column(Integer)
    local_ip: Mapped[str | None] = mapped_column(String(45))
    local_port: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    transport_connected_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    established_at: Mapped[Any | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    disconnected_at: Mapped[Any | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    disconnect_reason: Mapped[str | None] = mapped_column(String(40))
    disconnect_initiator: Mapped[str | None] = mapped_column(String(16))
    close_detail: Mapped[str | None] = mapped_column(String(512))
    client_identity_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    security_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    rx_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tx_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    rx_messages: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tx_messages: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    end_time_accuracy: Mapped[str] = mapped_column(String(16), nullable=False, default="exact")

    __table_args__ = (
        Index("ix_connection_session_channel_end", "channel_id", "disconnected_at"),
        Index("ix_connection_session_channel_reason", "channel_id", "disconnect_reason", "disconnected_at"),
        {"comment": "服务端客户端连接会话"},
    )

    @staticmethod
    def _json_object(value: str | None) -> dict[str, Any]:
        try:
            decoded = json.loads(value or "{}")
        except (TypeError, ValueError):
            return {}
        return decoded if isinstance(decoded, dict) else {}

    @staticmethod
    def _iso(value: Any) -> str | None:
        if value is None:
            return None
        # SQLite stores UTC but returns naive datetimes; attach UTC so the
        # browser renders the correct local time instead of the UTC clock time.
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "channel_id": self.channel_id,
            "protocol_type": self.protocol_type,
            "server_instance_id": self.server_instance_id,
            "state": self.state,
            "remote_ip": self.remote_ip,
            "remote_port": self.remote_port,
            "local_ip": self.local_ip,
            "local_port": self.local_port,
            "transport_connected_at": self._iso(self.transport_connected_at),
            "established_at": self._iso(self.established_at),
            "last_activity_at": self._iso(self.last_activity_at),
            "disconnected_at": self._iso(self.disconnected_at),
            "duration_ms": self.duration_ms,
            "disconnect_reason": self.disconnect_reason,
            "disconnect_initiator": self.disconnect_initiator,
            "close_detail": self.close_detail,
            "client_identity": self._json_object(self.client_identity_json),
            "security": self._json_object(self.security_json),
            "rx_bytes": self.rx_bytes,
            "tx_bytes": self.tx_bytes,
            "rx_messages": self.rx_messages,
            "tx_messages": self.tx_messages,
            "error_count": self.error_count,
            "end_time_accuracy": self.end_time_accuracy,
        }
