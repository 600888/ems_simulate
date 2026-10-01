"""Real asyncua client/server traffic for the first OPC UA milestone."""

from datetime import datetime
import socket

import pytest

from src.proto.opcua.core.transport import UaClientCore, UaServerCore, loopback_endpoint, make_endpoint_url
from src.proto.opcua.core.types import _json_value


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.asyncio
async def test_loopback_browse_read_write_and_release_port():
    port = _free_port()
    definitions = [
        {
            "node_id": "ns=2;s=test.enabled",
            "browse_name": "Enabled",
            "data_type": "Boolean",
            "initial_value": False,
            "writable": True,
        },
        {
            "node_id": "ns=2;s=test.count",
            "browse_name": "Count",
            "data_type": "Int32",
            "initial_value": 0,
            "writable": True,
        },
        {
            "node_id": "ns=2;s=test.power",
            "browse_name": "Power",
            "data_type": "Double",
            "initial_value": 0.0,
            "writable": True,
        },
    ]
    server = UaServerCore("127.0.0.1", port, "urn:ems:test", definitions=definitions)
    client = UaClientCore(server.endpoint_url)
    try:
        await server.start()
        await client.start()
        children = await client.browse()
        assert any(item["node_id"] == "ns=2;s=test.enabled" for item in children)
        page = await client.browse_page(limit=2, offset=1)
        assert page["total"] >= 3 and len(page["nodes"]) == 2
        assert page["offset"] == 1 and page["has_more"]
        with pytest.raises(ValueError, match="NodeId"):
            await client.read("invalid-node")
        assert (await client.read("ns=2;s=test.enabled"))["value"] is False
        result = await client.write("ns=2;s=test.enabled", True)
        assert result["value"] is True
        assert result["status_code"] == "Good"
        assert (await client.write("ns=2;s=test.count", 7))["value"] == 7
        assert (await client.write("ns=2;s=test.power", 12.5))["value"] == 12.5
        with pytest.raises(ValueError, match="范围"):
            await client.write("ns=2;s=test.count", 2**31)
        assert (await client.read("ns=2;s=test.count"))["value"] == 7
        with pytest.raises(ValueError, match="有限"):
            await client.write("ns=2;s=test.power", float("nan"))
        assert (await client.read("ns=2;s=test.power"))["value"] == 12.5
        with pytest.raises(ValueError, match="Boolean"):
            await client.write("ns=2;s=test.enabled", 1)
    finally:
        await client.stop()
        await server.stop()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))


def test_no_security_is_loopback_only():
    assert loopback_endpoint("opc.tcp://127.0.0.1:4840/ems/")
    assert make_endpoint_url("::1", 4840) == "opc.tcp://[::1]:4840/ems/"
    with pytest.raises(ValueError, match="loopback"):
        loopback_endpoint("opc.tcp://0.0.0.0:4840/ems/")


def test_utc_and_bounded_json_values():
    assert _json_value(datetime(2026, 10, 1, 0, 0)) == "2026-10-01T00:00:00+00:00"
    with pytest.raises(ValueError, match="上限"):
        _json_value(list(range(1001)))


@pytest.mark.asyncio
async def test_failed_bind_does_not_poison_retry():
    port = _free_port()
    first = UaServerCore("127.0.0.1", port, "urn:ems:first")
    second = UaServerCore("127.0.0.1", port, "urn:ems:second")
    await first.start()
    try:
        with pytest.raises(OSError):
            await second.start()
        assert not second.running
    finally:
        await first.stop()
    await second.start()
    await second.stop()
