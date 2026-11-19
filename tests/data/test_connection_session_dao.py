from dataclasses import replace
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.data.dao.connection_session_dao as dao_module
from src.data.dao.connection_session_dao import ConnectionSessionDao
from src.data.model import Base
from src.data.model.channel import Channel
from src.device.core.connection import (
    ConnectionSnapshot,
    ConnectionState,
    DisconnectInitiator,
    DisconnectReason,
)
from src.device.core.connection.persistence import ConnectionPersistenceWorker
from src.device.core.connection.registry import ConnectionSessionRegistry


def _session_factory(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(dao_module, "local_session", factory)
    with factory() as session, session.begin():
        session.add(
            Channel(
                id=1,
                code="connection-test",
                name="connection-test",
                protocol_type=1,
                conn_type=2,
                rtu_addr="1",
                timeout=5,
                enable=True,
                dlt645_point_mode="import",
            )
        )
    return factory


def _snapshot(index: int, *, terminal: bool = True) -> ConnectionSnapshot:
    started = datetime(2026, 8, 23, tzinfo=UTC) + timedelta(seconds=index)
    return ConnectionSnapshot(
        session_id=f"00000000-0000-0000-0000-{index:012d}",
        channel_id=1,
        protocol_type="ModbusTcpServer",
        server_instance_id="server-1",
        connection_key=f"connection-{index}",
        state=ConnectionState.CLOSED if terminal else ConnectionState.ESTABLISHED,
        remote_ip=f"192.0.2.{index % 255}",
        remote_port=40000 + index,
        local_ip="127.0.0.1",
        local_port=502,
        transport_connected_at=started,
        established_at=started,
        last_activity_at=started + timedelta(milliseconds=500),
        disconnected_at=started + timedelta(seconds=1) if terminal else None,
        duration_ms=1000 if terminal else 0,
        disconnect_reason=DisconnectReason.REMOTE_CLOSED if terminal else None,
        disconnect_initiator=DisconnectInitiator.REMOTE if terminal else None,
    )


def test_history_retains_latest_100_per_channel(monkeypatch):
    _session_factory(monkeypatch)
    for index in range(101):
        ConnectionSessionDao.save_snapshot(_snapshot(index))

    items, total = ConnectionSessionDao.list_history(1, page=1, page_size=100)
    assert total == 100
    assert len(items) == 100
    assert items[0]["session_id"].endswith("000000000100")
    assert all(not item["session_id"].endswith("000000000000") for item in items)


def test_startup_reconciles_unclosed_rows_without_inventing_end_time(monkeypatch):
    _session_factory(monkeypatch)
    ConnectionSessionDao.save_snapshot(_snapshot(1, terminal=False))

    assert ConnectionSessionDao.reconcile_incomplete() == 1
    detail = ConnectionSessionDao.get_detail(1, "00000000-0000-0000-0000-000000000001")
    assert detail is not None
    assert detail["state"] == "abnormal"
    assert detail["disconnect_reason"] == "process_terminated"
    assert detail["disconnected_at"] is None
    assert detail["end_time_accuracy"] == "estimated"


def test_batch_applies_open_then_close_and_ignores_deleted_channel(monkeypatch):
    _session_factory(monkeypatch)
    opened = _snapshot(5, terminal=False)
    closed = _snapshot(5, terminal=True)
    deleted_channel = replace(_snapshot(6, terminal=True), channel_id=999)

    ConnectionSessionDao.save_snapshots([opened, closed, deleted_channel])

    detail = ConnectionSessionDao.get_detail(1, closed.session_id)
    assert detail is not None
    assert detail["state"] == "closed"
    assert ConnectionSessionDao.get_detail(999, deleted_channel.session_id) is None


def test_clear_history_is_device_scoped_and_preserves_online_records(monkeypatch):
    factory = _session_factory(monkeypatch)
    with factory() as session, session.begin():
        session.add(Channel(id=2, code="other-server", name="other-server"))
    active = _snapshot(1, terminal=False)
    abnormal = replace(
        _snapshot(3),
        state=ConnectionState.ABNORMAL,
        disconnect_reason=DisconnectReason.NETWORK_RESET,
    )
    other = replace(_snapshot(5), channel_id=2)
    ConnectionSessionDao.save_snapshots([active, _snapshot(2), abnormal, _snapshot(4, terminal=False), other])

    assert ConnectionSessionDao.clear_history(1, active_session_ids=[active.session_id]) == 3
    assert ConnectionSessionDao.list_history(1)[1] == 0
    assert ConnectionSessionDao.summary_stats(1) == {"history_count": 0, "abnormal_disconnects_today": 0}
    assert ConnectionSessionDao.get_detail(1, active.session_id)["state"] == "established"
    assert ConnectionSessionDao.list_history(2)[1] == 1
    assert ConnectionSessionDao.clear_history(1, active_session_ids=[active.session_id]) == 0


def test_clear_discards_delayed_history_writes_and_keeps_future_disconnects(monkeypatch):
    _session_factory(monkeypatch)
    registry = ConnectionSessionRegistry()
    monkeypatch.setattr("src.device.core.connection.persistence.connection_registry", registry)
    snapshots = []
    registry.set_event_sink(lambda _event, snapshot: snapshots.append(snapshot))
    common = {"channel_id": 1, "protocol_type": "ModbusTcpServer", "server_instance_id": "server"}
    active_id = registry.open_session(**common, connection_key="active")
    closed_id = registry.open_session(**common, connection_key="closed")
    ConnectionSessionDao.save_snapshots(snapshots)
    registry.close_session(closed_id)
    # The database still says established; the terminal snapshot is waiting to be written.
    assert ConnectionSessionDao.get_detail(1, closed_id)["state"] == "established"
    worker = ConnectionPersistenceWorker()
    assert worker.clear_history(1) == 1

    worker._write_batch(snapshots)
    assert ConnectionSessionDao.get_detail(1, closed_id) is None
    assert ConnectionSessionDao.list_history(1)[1] == 0
    assert registry.get_current(1, active_id) is not None
    assert ConnectionSessionDao.get_detail(1, active_id)["state"] == "established"

    registry.close_session(active_id, reason=DisconnectReason.REMOTE_CLOSED)
    worker._write_batch([snapshots[-1]])
    assert ConnectionSessionDao.list_history(1)[1] == 1
    assert ConnectionSessionDao.get_detail(1, active_id)["state"] == "closed"
