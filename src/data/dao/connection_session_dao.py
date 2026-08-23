"""Database access for bounded server connection history."""

from datetime import UTC, datetime
import json
from typing import Any

from sqlalchemy import delete, func, or_, select

from src.data.controller.db import local_session
from src.data.model.channel import Channel
from src.data.model.connection_session import ConnectionSession
from src.device.core.connection.models import ConnectionSnapshot

TERMINAL_STATES = ("closed", "abnormal")


class ConnectionSessionDao:
    @staticmethod
    def _values(snapshot: ConnectionSnapshot) -> dict[str, Any]:
        return {
            "session_id": snapshot.session_id,
            "channel_id": snapshot.channel_id,
            "protocol_type": snapshot.protocol_type,
            "server_instance_id": snapshot.server_instance_id,
            "remote_ip": snapshot.remote_ip,
            "remote_port": snapshot.remote_port,
            "local_ip": snapshot.local_ip,
            "local_port": snapshot.local_port,
            "state": snapshot.state.value,
            "transport_connected_at": snapshot.transport_connected_at,
            "established_at": snapshot.established_at,
            "last_activity_at": snapshot.last_activity_at,
            "disconnected_at": snapshot.disconnected_at,
            "duration_ms": snapshot.duration_ms,
            "disconnect_reason": snapshot.disconnect_reason.value if snapshot.disconnect_reason else None,
            "disconnect_initiator": snapshot.disconnect_initiator.value if snapshot.disconnect_initiator else None,
            "close_detail": snapshot.close_detail,
            "client_identity_json": json.dumps(snapshot.client_identity, ensure_ascii=False, separators=(",", ":")),
            "security_json": json.dumps(snapshot.security, ensure_ascii=False, separators=(",", ":")),
            "rx_bytes": snapshot.rx_bytes,
            "tx_bytes": snapshot.tx_bytes,
            "rx_messages": snapshot.rx_messages,
            "tx_messages": snapshot.tx_messages,
            "error_count": snapshot.error_count,
            "end_time_accuracy": snapshot.end_time_accuracy,
        }

    @classmethod
    def save_snapshot(cls, snapshot: ConnectionSnapshot, *, retention_limit: int = 100) -> None:
        cls.save_snapshots([snapshot], retention_limit=retention_limit)

    @classmethod
    def save_snapshots(
        cls,
        snapshots: list[ConnectionSnapshot],
        *,
        retention_limit: int = 100,
    ) -> None:
        valid_snapshots = [snapshot for snapshot in snapshots if snapshot.channel_id > 0]
        if not valid_snapshots:
            return
        terminal_channels: set[int] = set()
        with local_session() as session, session.begin():
            requested_channel_ids = {snapshot.channel_id for snapshot in valid_snapshots}
            existing_channel_ids = set(
                session.scalars(select(Channel.id).where(Channel.id.in_(requested_channel_ids))).all()
            )
            valid_snapshots = [snapshot for snapshot in valid_snapshots if snapshot.channel_id in existing_channel_ids]
            session_ids = {snapshot.session_id for snapshot in valid_snapshots}
            rows_by_session_id = {
                row.session_id: row
                for row in session.scalars(
                    select(ConnectionSession).where(ConnectionSession.session_id.in_(session_ids))
                ).all()
            }
            for snapshot in valid_snapshots:
                values = cls._values(snapshot)
                row = rows_by_session_id.get(snapshot.session_id)
                if row is None:
                    row = ConnectionSession(**values)
                    session.add(row)
                    rows_by_session_id[snapshot.session_id] = row
                elif row.state not in TERMINAL_STATES or snapshot.state.value in TERMINAL_STATES:
                    for name, value in values.items():
                        setattr(row, name, value)
                if snapshot.state.value in TERMINAL_STATES:
                    terminal_channels.add(snapshot.channel_id)
            session.flush()
            for channel_id in terminal_channels:
                cls._prune(session, channel_id, retention_limit)

    @staticmethod
    def _prune(session: Any, channel_id: int, retention_limit: int) -> None:
        limit = max(1, int(retention_limit))
        retained = session.scalars(
            select(ConnectionSession.id)
            .where(ConnectionSession.channel_id == channel_id, ConnectionSession.state.in_(TERMINAL_STATES))
            .order_by(
                func.coalesce(
                    ConnectionSession.disconnected_at,
                    ConnectionSession.last_activity_at,
                    ConnectionSession.transport_connected_at,
                ).desc(),
                ConnectionSession.id.desc(),
            )
            .limit(limit)
        ).all()
        if not retained:
            return
        session.execute(
            delete(ConnectionSession).where(
                ConnectionSession.channel_id == channel_id,
                ConnectionSession.state.in_(TERMINAL_STATES),
                ConnectionSession.id.not_in(retained),
            )
        )

    @classmethod
    def reconcile_incomplete(cls) -> int:
        """Convert rows left open by a previous process into estimated abnormal history."""
        updated = 0
        with local_session() as session, session.begin():
            rows = session.scalars(
                select(ConnectionSession).where(ConnectionSession.state.not_in(TERMINAL_STATES))
            ).all()
            channel_ids: set[int] = set()
            for row in rows:
                end = row.last_activity_at or row.transport_connected_at
                start = row.established_at or row.transport_connected_at
                duration = max(0, int((end - start).total_seconds() * 1000)) if end and start else 0
                row.state = "abnormal"
                row.disconnect_reason = "process_terminated"
                row.disconnect_initiator = "process"
                row.disconnected_at = None
                row.duration_ms = duration
                row.end_time_accuracy = "estimated"
                channel_ids.add(row.channel_id)
                updated += 1
            session.flush()
            for channel_id in channel_ids:
                cls._prune(session, channel_id, 100)
        return updated

    @classmethod
    def list_history(
        cls,
        channel_id: int,
        *,
        page: int = 1,
        page_size: int = 20,
        disconnect_reason: str | None = None,
        remote_ip: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        conditions = [ConnectionSession.channel_id == channel_id, ConnectionSession.state.in_(TERMINAL_STATES)]
        if disconnect_reason:
            conditions.append(ConnectionSession.disconnect_reason == disconnect_reason)
        if remote_ip:
            conditions.append(ConnectionSession.remote_ip == remote_ip)
        order_key = func.coalesce(
            ConnectionSession.disconnected_at,
            ConnectionSession.last_activity_at,
            ConnectionSession.transport_connected_at,
        )
        with local_session() as session:
            total = session.scalar(select(func.count(ConnectionSession.id)).where(*conditions)) or 0
            rows = session.scalars(
                select(ConnectionSession)
                .where(*conditions)
                .order_by(order_key.desc(), ConnectionSession.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return [row.to_dict() for row in rows], int(total)

    @classmethod
    def get_detail(cls, channel_id: int, session_id: str) -> dict[str, Any] | None:
        with local_session() as session:
            row = session.scalar(
                select(ConnectionSession).where(
                    ConnectionSession.channel_id == channel_id,
                    ConnectionSession.session_id == session_id,
                )
            )
            return row.to_dict() if row else None

    @classmethod
    def summary_stats(cls, channel_id: int) -> dict[str, int]:
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        with local_session() as session:
            history_count = (
                session.scalar(
                    select(func.count(ConnectionSession.id)).where(
                        ConnectionSession.channel_id == channel_id,
                        ConnectionSession.state.in_(TERMINAL_STATES),
                    )
                )
                or 0
            )
            abnormal_today = (
                session.scalar(
                    select(func.count(ConnectionSession.id)).where(
                        ConnectionSession.channel_id == channel_id,
                        ConnectionSession.state == "abnormal",
                        or_(ConnectionSession.disconnected_at >= today, ConnectionSession.last_activity_at >= today),
                    )
                )
                or 0
            )
        return {"history_count": int(history_count), "abnormal_disconnects_today": int(abnormal_today)}

    @classmethod
    def delete_by_channel(cls, channel_id: int) -> None:
        with local_session() as session, session.begin():
            session.execute(delete(ConnectionSession).where(ConnectionSession.channel_id == channel_id))
