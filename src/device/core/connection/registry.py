"""Thread-safe in-memory truth for current server-side client sessions."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
import threading
import time
from typing import Any
import unicodedata
from uuid import uuid4

from .models import (
    ABNORMAL_REASONS,
    ConnectionSnapshot,
    ConnectionState,
    DisconnectInitiator,
    DisconnectReason,
    endpoint_parts,
    utc_now,
)

ConnectionEventSink = Callable[[str, ConnectionSnapshot], None]


def _safe_close_detail(detail: str | None) -> str | None:
    if not detail:
        return None
    cleaned = "".join(" " if unicodedata.category(char).startswith("C") else char for char in str(detail))
    return cleaned.strip()[:512] or None


@dataclass(slots=True)
class _ConnectionSession:
    session_id: str
    channel_id: int
    protocol_type: str
    server_instance_id: str
    connection_key: str
    remote_ip: str | None
    remote_port: int | None
    local_ip: str | None
    local_port: int | None
    transport_connected_at: datetime
    established_at: datetime | None
    last_activity_at: datetime
    started_monotonic_ns: int
    last_activity_monotonic_ns: int
    state: ConnectionState = ConnectionState.ESTABLISHED
    disconnected_at: datetime | None = None
    disconnected_monotonic_ns: int | None = None
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
    last_checkpoint_monotonic_ns: int = 0

    def snapshot(self, now_monotonic_ns: int | None = None) -> ConnectionSnapshot:
        end_ns = self.disconnected_monotonic_ns
        if end_ns is None:
            end_ns = now_monotonic_ns if now_monotonic_ns is not None else time.monotonic_ns()
        duration_ms = max(0, (end_ns - self.started_monotonic_ns) // 1_000_000)
        return ConnectionSnapshot(
            session_id=self.session_id,
            channel_id=self.channel_id,
            protocol_type=self.protocol_type,
            server_instance_id=self.server_instance_id,
            connection_key=self.connection_key,
            state=self.state,
            remote_ip=self.remote_ip,
            remote_port=self.remote_port,
            local_ip=self.local_ip,
            local_port=self.local_port,
            transport_connected_at=self.transport_connected_at,
            established_at=self.established_at,
            last_activity_at=self.last_activity_at,
            disconnected_at=self.disconnected_at,
            duration_ms=duration_ms,
            disconnect_reason=self.disconnect_reason,
            disconnect_initiator=self.disconnect_initiator,
            close_detail=self.close_detail,
            client_identity=dict(self.client_identity),
            security=dict(self.security),
            rx_bytes=self.rx_bytes,
            tx_bytes=self.tx_bytes,
            rx_messages=self.rx_messages,
            tx_messages=self.tx_messages,
            error_count=self.error_count,
        )


class ConnectionSessionRegistry:
    """O(1) lifecycle updates safe for asyncio, worker and native callback threads."""

    def __init__(self, checkpoint_interval_seconds: float = 30.0) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, _ConnectionSession] = {}
        self._key_index: dict[tuple[int, str, str], str] = {}
        self._event_sink: ConnectionEventSink | None = None
        self._checkpoint_ns = max(1, int(checkpoint_interval_seconds * 1_000_000_000))

    def set_event_sink(self, sink: ConnectionEventSink | None) -> None:
        with self._lock:
            self._event_sink = sink

    def _emit(self, event: str, snapshot: ConnectionSnapshot) -> None:
        with self._lock:
            sink = self._event_sink
        if sink is not None:
            sink(event, snapshot)

    def open_session(
        self,
        *,
        channel_id: int,
        protocol_type: str,
        server_instance_id: str,
        connection_key: str,
        remote_endpoint: Any = None,
        local_endpoint: Any = None,
        client_identity: dict[str, Any] | None = None,
        security: dict[str, Any] | None = None,
        connected_at: datetime | None = None,
        state: ConnectionState = ConnectionState.ESTABLISHED,
    ) -> str:
        scoped_key = (channel_id, server_instance_id, str(connection_key))
        with self._lock:
            previous_id = self._key_index.get(scoped_key)
        if previous_id:
            self.close_session(
                previous_id,
                reason=DisconnectReason.CONNECTION_REPLACED,
                initiator=DisconnectInitiator.SERVER,
            )

        now = connected_at or utc_now()
        monotonic_ns = time.monotonic_ns()
        remote_ip, remote_port = endpoint_parts(remote_endpoint)
        local_ip, local_port = endpoint_parts(local_endpoint)
        session = _ConnectionSession(
            session_id=str(uuid4()),
            channel_id=int(channel_id),
            protocol_type=str(protocol_type),
            server_instance_id=server_instance_id,
            connection_key=str(connection_key),
            remote_ip=remote_ip,
            remote_port=remote_port,
            local_ip=local_ip,
            local_port=local_port,
            transport_connected_at=now,
            established_at=now if state != ConnectionState.CONNECTING else None,
            last_activity_at=now,
            started_monotonic_ns=monotonic_ns,
            last_activity_monotonic_ns=monotonic_ns,
            last_checkpoint_monotonic_ns=monotonic_ns,
            state=state,
            client_identity=dict(client_identity or {}),
            security=dict(security or {}),
        )
        with self._lock:
            self._sessions[session.session_id] = session
            self._key_index[scoped_key] = session.session_id
            snapshot = session.snapshot(monotonic_ns)
        self._emit("opened", snapshot)
        return session.session_id

    def update_session(
        self,
        session_id: str,
        *,
        state: ConnectionState | None = None,
        remote_endpoint: Any = None,
        local_endpoint: Any = None,
        client_identity: dict[str, Any] | None = None,
        security: dict[str, Any] | None = None,
    ) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.disconnected_at is not None:
                return False
            if state is not None:
                session.state = state
                if state in (ConnectionState.ESTABLISHED, ConnectionState.ACTIVE) and session.established_at is None:
                    session.established_at = utc_now()
            if remote_endpoint is not None:
                session.remote_ip, session.remote_port = endpoint_parts(remote_endpoint)
            if local_endpoint is not None:
                session.local_ip, session.local_port = endpoint_parts(local_endpoint)
            if client_identity:
                session.client_identity.update(client_identity)
            if security:
                session.security.update(security)
            snapshot = session.snapshot()
        self._emit("updated", snapshot)
        return True

    def record_activity(
        self,
        session_id: str,
        *,
        rx_bytes: int = 0,
        tx_bytes: int = 0,
        rx_messages: int = 0,
        tx_messages: int = 0,
        errors: int = 0,
    ) -> bool:
        checkpoint = False
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.disconnected_at is not None:
                return False
            now = utc_now()
            now_ns = time.monotonic_ns()
            session.last_activity_at = now
            session.last_activity_monotonic_ns = now_ns
            session.rx_bytes += max(0, int(rx_bytes))
            session.tx_bytes += max(0, int(tx_bytes))
            session.rx_messages += max(0, int(rx_messages))
            session.tx_messages += max(0, int(tx_messages))
            session.error_count += max(0, int(errors))
            session.state = ConnectionState.ACTIVE
            if now_ns - session.last_checkpoint_monotonic_ns >= self._checkpoint_ns:
                session.last_checkpoint_monotonic_ns = now_ns
                checkpoint = True
                snapshot = session.snapshot(now_ns)
        if checkpoint:
            self._emit("activity", snapshot)
        return True

    def close_session(
        self,
        session_id: str,
        *,
        reason: DisconnectReason = DisconnectReason.UNKNOWN,
        initiator: DisconnectInitiator = DisconnectInitiator.UNKNOWN,
        detail: str | None = None,
        disconnected_at: datetime | None = None,
        final_stats: dict[str, int] | None = None,
    ) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.disconnected_at is not None:
                return False
            if final_stats:
                for name in ("rx_bytes", "tx_bytes", "rx_messages", "tx_messages", "error_count"):
                    if name in final_stats:
                        setattr(session, name, max(getattr(session, name), max(0, int(final_stats[name]))))
            session.disconnected_at = disconnected_at or utc_now()
            session.disconnected_monotonic_ns = time.monotonic_ns()
            session.disconnect_reason = reason
            session.disconnect_initiator = initiator
            session.close_detail = _safe_close_detail(detail)
            session.state = ConnectionState.ABNORMAL if reason in ABNORMAL_REASONS else ConnectionState.CLOSED
            scoped_key = (session.channel_id, session.server_instance_id, session.connection_key)
            self._key_index.pop(scoped_key, None)
            self._sessions.pop(session_id, None)
            snapshot = session.snapshot(session.disconnected_monotonic_ns)
        self._emit("closed", snapshot)
        return True

    def close_server_sessions(
        self,
        channel_id: int,
        server_instance_id: str,
        *,
        reason: DisconnectReason = DisconnectReason.SERVER_STOPPED,
    ) -> int:
        with self._lock:
            session_ids = [
                item.session_id
                for item in self._sessions.values()
                if item.channel_id == channel_id and item.server_instance_id == server_instance_id
            ]
        return sum(
            self.close_session(session_id, reason=reason, initiator=DisconnectInitiator.SERVER)
            for session_id in session_ids
        )

    def current(self, channel_id: int) -> tuple[ConnectionSnapshot, ...]:
        now_ns = time.monotonic_ns()
        with self._lock:
            items = [item.snapshot(now_ns) for item in self._sessions.values() if item.channel_id == channel_id]
        return tuple(sorted(items, key=lambda item: item.transport_connected_at, reverse=True))

    def get_current(self, channel_id: int, session_id: str) -> ConnectionSnapshot | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.channel_id != channel_id:
                return None
            return session.snapshot()

    def summary(self, channel_id: int) -> dict[str, int]:
        items = self.current(channel_id)
        return {
            "current_count": len(items),
            "active_count": sum(item.state == ConnectionState.ACTIVE for item in items),
            "idle_count": sum(item.state == ConnectionState.IDLE for item in items),
        }


connection_registry = ConnectionSessionRegistry()
