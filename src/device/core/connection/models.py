"""Protocol-neutral server connection session models."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class ConnectionState(StrEnum):
    CONNECTING = "connecting"
    ESTABLISHED = "established"
    ACTIVE = "active"
    IDLE = "idle"
    CLOSED = "closed"
    ABNORMAL = "abnormal"


class DisconnectReason(StrEnum):
    REMOTE_CLOSED = "remote_closed"
    NETWORK_RESET = "network_reset"
    IDLE_TIMEOUT = "idle_timeout"
    PROTOCOL_ERROR = "protocol_error"
    TLS_HANDSHAKE_FAILED = "tls_handshake_failed"
    AUTHENTICATION_FAILED = "authentication_failed"
    SERVER_STOPPED = "server_stopped"
    CONNECTION_REPLACED = "connection_replaced"
    MAX_CONNECTIONS_REJECTED = "max_connections_rejected"
    PROCESS_TERMINATED = "process_terminated"
    UNKNOWN = "unknown"


class DisconnectInitiator(StrEnum):
    REMOTE = "remote"
    SERVER = "server"
    NETWORK = "network"
    PROCESS = "process"
    UNKNOWN = "unknown"


ABNORMAL_REASONS = {
    DisconnectReason.NETWORK_RESET,
    DisconnectReason.PROTOCOL_ERROR,
    DisconnectReason.TLS_HANDSHAKE_FAILED,
    DisconnectReason.AUTHENTICATION_FAILED,
    DisconnectReason.PROCESS_TERMINATED,
    DisconnectReason.UNKNOWN,
}


def utc_now() -> datetime:
    return datetime.now(UTC)


def _serialize_dt(value: datetime | None) -> str | None:
    """Serialize a datetime to ISO-8601 with an explicit UTC offset.

    Some protocol libs (c104) and SQLite hand back *naive* datetimes whose
    wall-clock value is actually UTC. Without an explicit offset the browser
    parses them as local time and renders the UTC clock time (off by the TZ
    offset) — so attach UTC when tzinfo is missing.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def endpoint_parts(endpoint: Any) -> tuple[str | None, int | None]:
    """Normalize socket-style endpoints, including IPv6 four-tuples."""
    if not endpoint:
        return None, None
    if isinstance(endpoint, (tuple, list)) and endpoint:
        ip = str(endpoint[0]) if endpoint[0] is not None else None
        try:
            port = int(endpoint[1]) if len(endpoint) > 1 and endpoint[1] is not None else None
        except (TypeError, ValueError):
            port = None
        return ip, port
    if isinstance(endpoint, str):
        value = endpoint.strip()
        if value.startswith("[") and "]:" in value:
            host, port_text = value[1:].rsplit("]:", 1)
            if port_text.isdigit():
                return host, int(port_text)
        if value.count(":") == 1:
            host, port_text = value.rsplit(":", 1)
            if port_text.isdigit():
                return host, int(port_text)
        return value, None
    return str(endpoint), None


@dataclass(frozen=True, slots=True)
class ConnectionSnapshot:
    session_id: str
    channel_id: int
    protocol_type: str
    server_instance_id: str
    connection_key: str
    state: ConnectionState
    remote_ip: str | None
    remote_port: int | None
    local_ip: str | None
    local_port: int | None
    transport_connected_at: datetime
    established_at: datetime | None
    last_activity_at: datetime
    disconnected_at: datetime | None
    duration_ms: int
    disconnect_reason: DisconnectReason | None = None
    disconnect_initiator: DisconnectInitiator | None = None
    close_detail: str | None = None
    client_identity: dict[str, Any] = field(default_factory=dict)
    security: dict[str, Any] = field(default_factory=dict)
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_messages: int = 0
    tx_messages: int = 0
    error_count: int = 0
    end_time_accuracy: str = "exact"

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "channel_id": self.channel_id,
            "protocol_type": self.protocol_type,
            "server_instance_id": self.server_instance_id,
            "state": self.state.value,
            "remote_ip": self.remote_ip,
            "remote_port": self.remote_port,
            "local_ip": self.local_ip,
            "local_port": self.local_port,
            "transport_connected_at": _serialize_dt(self.transport_connected_at),
            "established_at": _serialize_dt(self.established_at),
            "last_activity_at": _serialize_dt(self.last_activity_at),
            "disconnected_at": _serialize_dt(self.disconnected_at),
            "duration_ms": self.duration_ms,
            "disconnect_reason": self.disconnect_reason.value if self.disconnect_reason else None,
            "disconnect_initiator": self.disconnect_initiator.value if self.disconnect_initiator else None,
            "close_detail": self.close_detail,
            "client_identity": dict(self.client_identity),
            "security": dict(self.security),
            "rx_bytes": self.rx_bytes,
            "tx_bytes": self.tx_bytes,
            "rx_messages": self.rx_messages,
            "tx_messages": self.tx_messages,
            "error_count": self.error_count,
            "end_time_accuracy": self.end_time_accuracy,
        }
