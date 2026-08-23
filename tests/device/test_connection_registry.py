from concurrent.futures import ThreadPoolExecutor

from src.device.core.connection import (
    ConnectionSessionRegistry,
    ConnectionState,
    DisconnectInitiator,
    DisconnectReason,
)


def test_connection_lifecycle_is_idempotent_and_emits_immutable_snapshots():
    registry = ConnectionSessionRegistry(checkpoint_interval_seconds=0)
    events = []
    registry.set_event_sink(lambda event, snapshot: events.append((event, snapshot)))

    session_id = registry.open_session(
        channel_id=7,
        protocol_type="ModbusTcpServer",
        server_instance_id="server-1",
        connection_key="socket-1",
        remote_endpoint=("192.0.2.10", 41000),
        local_endpoint=("0.0.0.0", 502),
    )
    assert registry.record_activity(session_id, rx_bytes=12, rx_messages=1)
    assert registry.current(7)[0].state is ConnectionState.ACTIVE
    assert registry.current(7)[0].rx_bytes == 12

    assert registry.close_session(
        session_id,
        reason=DisconnectReason.REMOTE_CLOSED,
        initiator=DisconnectInitiator.REMOTE,
    )
    assert not registry.close_session(session_id)
    assert registry.current(7) == ()
    assert [event for event, _ in events] in (["opened", "closed"], ["opened", "activity", "closed"])
    assert events[-1][1].duration_ms >= 0
    assert events[-1][1].state is ConnectionState.CLOSED


def test_reusing_protocol_connection_key_closes_previous_session():
    registry = ConnectionSessionRegistry()
    closed = []
    registry.set_event_sink(lambda event, snapshot: closed.append(snapshot) if event == "closed" else None)

    first = registry.open_session(
        channel_id=3,
        protocol_type="Dnp3Server",
        server_instance_id="server-1",
        connection_key="active",
    )
    second = registry.open_session(
        channel_id=3,
        protocol_type="Dnp3Server",
        server_instance_id="server-1",
        connection_key="active",
    )

    assert first != second
    assert len(registry.current(3)) == 1
    assert closed[0].session_id == first
    assert closed[0].disconnect_reason is DisconnectReason.CONNECTION_REPLACED


def test_registry_handles_parallel_open_and_close_without_leaks():
    registry = ConnectionSessionRegistry()

    def connect(index: int) -> str:
        return registry.open_session(
            channel_id=9,
            protocol_type="Iec104Server",
            server_instance_id="server-1",
            connection_key=f"connection-{index}",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        session_ids = list(executor.map(connect, range(100)))
        results = list(
            executor.map(
                lambda session_id: registry.close_session(
                    session_id,
                    reason=DisconnectReason.SERVER_STOPPED,
                    initiator=DisconnectInitiator.SERVER,
                ),
                session_ids,
            )
        )

    assert all(results)
    assert registry.current(9) == ()
