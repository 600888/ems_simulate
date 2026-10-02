"""Server object inspection and live values use the actual running address space."""

import socket

from pydantic import ValidationError as PydanticValidationError
import pytest
import pytest_asyncio

from src.device.protocol.opcua_handler import OpcUaClientHandler, OpcUaServerHandler
from src.proto.opcua.client import OpcUaClient
from src.proto.opcua.server import OpcUaServer
from src.web.api.exceptions import OperationError, ValidationError
import src.web.api.opcua.router as api


@pytest_asyncio.fixture
async def running_server():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = OpcUaServer(
        "127.0.0.1",
        port,
        "urn:test:objects",
        definitions=[
            dict(node_id="ns=2;s=power", browse_name="Power", data_type="Double", initial_value=3, writable=True),
            dict(node_id="ns=2;s=locked", browse_name="Locked", data_type="Int64", initial_value=7, writable=False),
        ],
    )
    await server.start()
    try:
        yield server
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_real_objects_attributes_references_and_live_write(running_server):
    server = running_server
    first = await server.browse_page("i=85", 1)
    remaining = await server.browse_page("i=85", 50, 1)
    assert first["has_more"]
    nodes = first["nodes"] + remaining["nodes"]
    assert {n["node_id"] for n in nodes} >= {"i=2253", "ns=2;s=power", "ns=2;s=locked"}
    assert (await server.inspect_node("i=85"))["node_class"] == "Object"
    details = await server.inspect_node("ns=2;s=power")
    assert details["namespace_uri"] == "urn:test:objects"
    assert details["data_type"] == "Double"
    assert details["type_definition"] == "BaseDataVariableType"
    assert details["value_rank"] == -1 and details["writable"]
    assert any(r["node_id"] == "i=85" and not r["forward"] for r in details["references"])
    client = OpcUaClient(server.endpoint_url)
    try:
        await client.start()
        await client.write("ns=2;s=power", 42.5)
        assert (await server.read("ns=2;s=power"))["value"] == 42.5
        await server.write("ns=2;s=power", 91.0)
        assert (await client.read("ns=2;s=power"))["value"] == 91.0
    finally:
        await client.stop()
    with pytest.raises(ValueError, match="不允许写入"):
        await server.write("ns=2;s=locked", 99)
    assert (await server.read("ns=2;s=locked"))["value"] == 7


@pytest.mark.asyncio
async def test_server_routes_values_deduplication_invalid_node_and_stopped(monkeypatch, running_server):
    handler = object.__new__(OpcUaServerHandler)
    handler.server, handler._is_running = running_server, True
    monkeypatch.setattr(api, "_handler", lambda request, channel_id: handler)
    response = await api.server_values(api.ValuesRequest(channel_id=1, node_ids=["ns=2;s=power"] * 2), None)
    assert len(response.data["values"]) == 1
    assert response.data["values"][0]["status_code"] == "Good"
    missing = await api.server_values(api.ValuesRequest(channel_id=1, node_ids=["ns=2;s=missing"]), None)
    assert missing.data["values"][0]["status_code"] == "BadNodeIdUnknown"
    details = (await api.server_inspect(api.NodeRequest(channel_id=1, node_id="ns=2;s=power"), None)).data
    assert details["data_type"] == "Double"
    written = await api.server_write(api.WriteRequest(channel_id=1, node_id="ns=2;s=power", value=23.0), None)
    assert written.data["value"] == 23.0
    with pytest.raises(ValidationError, match="不允许写入"):
        await api.server_write(api.WriteRequest(channel_id=1, node_id="ns=2;s=locked", value=23), None)
    partial = await api.server_values(api.ValuesRequest(channel_id=1, node_ids=["bad id", "ns=2;s=power"]), None)
    assert partial.data["errors"][0]["node_id"] == "bad id"
    assert partial.data["values"][0]["node_id"] == "ns=2;s=power"
    handler._is_running = False
    with pytest.raises(OperationError, match="启动"):
        await api.server_browse(api.BrowseRequest(channel_id=1), None)
    monkeypatch.setattr(api, "_handler", lambda request, channel_id: object.__new__(OpcUaClientHandler))
    with pytest.raises(ValidationError, match="服务端"):
        await api.server_inspect(api.NodeRequest(channel_id=1, node_id="i=85"), None)


def test_snapshot_batch_is_bounded():
    with pytest.raises(PydanticValidationError):
        api.ValuesRequest(channel_id=1, node_ids=["ns=2;s=power"] * 51)
