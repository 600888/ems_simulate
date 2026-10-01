"""Real transport traffic through channel-scoped plugins and NodeSet export."""

import asyncio
import socket

from asyncua import Server, ua
import pytest

from src.proto.opcua.client import OpcUaClient
from src.proto.opcua.core.nodeset import inspect_nodeset
from src.proto.opcua.server import OpcUaServer


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def definitions() -> list[dict]:
    return [
        {
            "node_id": "ns=2;s=flag",
            "browse_name": "Flag",
            "data_type": "Boolean",
            "initial_value": False,
            "writable": True,
        },
        {
            "node_id": "ns=2;s=count",
            "browse_name": "Count",
            "data_type": "Int32",
            "initial_value": 7,
            "writable": False,
        },
        {
            "node_id": "ns=2;s=power",
            "browse_name": "Power",
            "data_type": "Double",
            "initial_value": 12.5,
            "writable": True,
        },
    ]


@pytest.mark.asyncio
async def test_plugins_are_channel_scoped_and_nodeset_roundtrips():
    model = definitions()
    server = OpcUaServer("127.0.0.1", free_port(), "urn:ems:facade", definitions=model, channel_id=1)
    other = OpcUaServer("127.0.0.1", free_port(), "urn:ems:other", definitions=model, channel_id=2)
    model[0]["initial_value"] = True
    client = OpcUaClient(server.endpoint_url, channel_id=3)
    try:
        await server.start()
        await client.start()
        assert server.node_count == 3
        await client.write("ns=2;s=flag", True)
        await client.write("ns=2;s=power", 99.0)
        assert await server.reset_values() == 3
        assert (await client.read("ns=2;s=flag"))["value"] is False
        assert (await server.read("ns=2;s=power"))["value"] == 12.5
        assert all(item["running"] for item in server.capabilities())
        assert not any(item["running"] for item in other.capabilities())
        xml = await server.export_nodeset()
        parsed = await inspect_nodeset(xml)
        assert parsed.namespace_uri == "urn:ems:facade"
        assert sorted(parsed.definitions, key=lambda item: item["node_id"]) == sorted(
            [{"namespace_uri": "urn:ems:facade", **item} for item in definitions()],
            key=lambda item: item["node_id"],
        )
        await client.stop()
        await server.stop()
        assert not any(item["running"] for item in server.capabilities())
        await server.start()
        await client.start()
        assert (await client.read("ns=2;s=count"))["value"] == 7
        assert server.node_count == 3
    finally:
        await client.stop()
        await server.stop()


@pytest.mark.asyncio
async def test_required_address_space_failure_releases_transport():
    port = free_port()
    model = definitions()
    model.append(model[0].copy())
    server = OpcUaServer("127.0.0.1", port, "urn:ems:duplicate", definitions=model)
    with pytest.raises(RuntimeError, match="重复 NodeId"):
        await server.start()
    assert not server.running
    assert not any(item["running"] for item in server.capabilities())
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", port))


@pytest.mark.asyncio
async def test_disabled_model_io_reports_reason_and_rejects_export():
    server = OpcUaServer(
        "127.0.0.1", free_port(), "urn:ems:disabled", definitions=definitions(), enabled_plugins={"address_space"}
    )
    try:
        await server.start()
        state = next(item for item in server.capabilities() if item["name"] == "model_io")
        assert state["enabled"] is False and state["reason"] == "已禁用"
        with pytest.raises(ValueError, match="不可用"):
            await server.export_nodeset()
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_client_detects_disconnection_and_can_connect_again():
    server = OpcUaServer("127.0.0.1", free_port(), "urn:ems:disconnect", definitions=definitions())
    client = OpcUaClient(server.endpoint_url)
    try:
        await server.start()
        await client.start()
        assert client.running
        await server.stop()
        async with asyncio.timeout(5):
            while client.running or client.connection_error is None:
                await asyncio.sleep(0.05)
        assert not client.running and client.connection_error
        await server.start()
        await client.start()
        assert client.running and client.connection_error is None
        assert (await client.read("ns=2;s=count"))["value"] == 7
    finally:
        await client.stop()
        await server.stop()


@pytest.mark.asyncio
async def test_imported_point_resolves_namespace_uri_and_preserves_bad_quality():
    server = Server()
    await server.init()
    endpoint = f"opc.tcp://127.0.0.1:{free_port()}/external/"
    server.set_endpoint(endpoint)
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
    await server.register_namespace("urn:other:namespace")
    index = await server.register_namespace("urn:external:model")
    assert index == 3
    variable = await server.nodes.objects.add_variable(ua.NodeId("power", index), "Power", 12.5)
    await variable.write_value(
        ua.DataValue(ua.Variant(12.5, ua.VariantType.Double), ua.StatusCode(ua.StatusCodes.BadOutOfService))
    )
    client = OpcUaClient(endpoint)
    try:
        await server.start()
        await client.start()
        snapshot = await client.read_point("urn:external:model", "ns=2;s=power")
        assert snapshot["node_id"] == "ns=3;s=power"
        assert snapshot["value"] is None and snapshot["status_code"] == "BadOutOfService"
        await variable.write_value(12.5, ua.VariantType.Double)
        assert (await client.read_point("urn:external:model", "ns=2;s=power"))["value"] == 12.5
        with pytest.raises(ValueError, match="命名空间 URI"):
            await client.read_point("urn:missing", "ns=2;s=power")
    finally:
        await client.stop()
        await server.stop()
