"""History persists across restarts; events and call summaries use real UA traffic."""

import asyncio
from datetime import UTC, datetime, timedelta
import socket

import pytest

from src.proto.opcua.client import OpcUaClient
from src.proto.opcua.server import OpcUaServer


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.asyncio
async def test_persistent_raw_history_and_real_event_subscription(tmp_path):
    definition = {
        "node_id": "ns=2;s=power",
        "browse_name": "Power",
        "data_type": "Double",
        "initial_value": 0.0,
        "writable": True,
    }
    server = OpcUaServer(
        "127.0.0.1",
        free_port(),
        "urn:test:history",
        definitions=[definition],
        features={
            "history": {"enabled": True, "nodes": [definition["node_id"]]},
            "history_path": str(tmp_path / "history.sqlite"),
            "events": {"enabled": True},
        },
    )
    client = OpcUaClient(server.endpoint_url, features={"events": {"enabled": True}})
    start = datetime.now(UTC) - timedelta(minutes=1)
    try:
        await server.start()
        await client.start()
        assert not [item for item in server.capabilities() if not item["running"]], [
            (item["name"], item["reason"]) for item in server.capabilities() if not item["running"]
        ]
        for value in [1.0, 2.0, 3.0]:
            await client.write(definition["node_id"], value)
            await asyncio.sleep(0.15)
        result = await client.read_history(definition["node_id"], start, datetime.now(UTC), 2)
        assert len(result["values"]) == 2
        if result["continuation"]:
            next_page = await client.read_history(
                definition["node_id"], start, datetime.now(UTC), 2, result["continuation"]
            )
            assert next_page["values"]
        await server.emit_event("Test event", 750)
        async with asyncio.timeout(5):
            while not any(item.get("Message") == "Test event" for item in client.stream.page()["events"]):
                await asyncio.sleep(0.05)
        assert any(call["service"] == "Write" for call in client.diagnostics()["calls"])
        assert any(call["service"] == "Write" for call in server.diagnostics()["calls"])
        assert any(session["state"] == "active" for session in server.diagnostics()["sessions"])
        assert "private_key" not in str(client.diagnostics())
        await client.stop()
        await server.stop()
        await server.start()
        await client.start()
        result = await client.read_history(definition["node_id"], start, datetime.now(UTC), 100)
        assert {1.0, 2.0, 3.0} <= {item["value"] for item in result["values"]}
    finally:
        await client.stop()
        await server.stop()
