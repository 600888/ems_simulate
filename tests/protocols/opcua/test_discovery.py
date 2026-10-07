"""Recursive discovery boundaries and real UA subscription integration."""

import asyncio
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock

from asyncua import ua
from fastapi import Request
import pytest

from src.device.protocol.opcua_handler import OpcUaClientHandler
from src.proto.opcua.client import OpcUaClient
from src.proto.opcua.core.discovery import discover_variables
from src.proto.opcua.core.transport import UaServerCore
from src.web.api.exceptions import OperationError, ValidationError
import src.web.api.opcua.router as api


@pytest.mark.asyncio
async def test_discovery_handles_cycles_aliases_depth_and_partial_errors():
    graph = {
        "i=85": ["ns=2;s=folder", "ns=2;s=bad", "i=2253"],
        "ns=2;s=folder": ["ns=0;i=85", "ns=2;s=value", "ns=2;s=folder"],
        "ns=2;s=value": [],
    }

    async def inspect(node_id):
        if node_id.endswith("bad"):
            raise RuntimeError("BadUserAccessDenied")
        return {
            "node_id": node_id,
            "node_class": "Variable" if node_id.endswith("value") else "Object",
            "readable": True,
            "namespace_index": 2 if node_id.startswith("ns=2;") else 0,
        }

    children = AsyncMock(side_effect=lambda node_id: graph[node_id])
    result = await discover_variables("ns=0;i=85", children, inspect)
    assert [node["node_id"] for node in result["nodes"]] == ["ns=2;s=value"]
    assert result["visited"] == 4 and not result["truncated"]
    assert result["errors"] == [{"node_id": "ns=2;s=bad", "message": "BadUserAccessDenied"}]
    assert "i=2253" not in [call.args[0] for call in children.call_args_list]
    shallow = await discover_variables("i=85", children, inspect, max_depth=1)
    assert shallow["nodes"] == [] and shallow["reason"] == "max_depth"
    limited = await discover_variables("i=85", children, inspect, max_nodes=1)
    assert len(limited["nodes"]) == 1 and limited["reason"] == "max_nodes"


@pytest.mark.asyncio
async def test_timeout_returns_partial_result_and_cancellation_propagates():
    async def inspect(node_id):
        if node_id.endswith("slow"):
            await asyncio.sleep(10)
        return {"node_id": node_id, "node_class": "Variable", "readable": True, "namespace_index": 2}

    async def children(node_id):
        return ["ns=2;s=slow"] if node_id.endswith("fast") else []

    result = await discover_variables("ns=2;s=fast", children, inspect, timeout_s=1)
    assert len(result["nodes"]) == 1 and result["reason"] == "timeout"
    task = asyncio.create_task(discover_variables("ns=2;s=slow", children, inspect))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_root_failure_is_not_reported_as_success():
    with pytest.raises(RuntimeError, match="root missing"):
        await discover_variables("i=85", AsyncMock(), AsyncMock(side_effect=RuntimeError("root missing")))


@pytest.mark.asyncio
async def test_standard_namespace_filter_and_global_visit_limit():
    async def inspect(node_id):
        return {
            "node_id": node_id,
            "node_class": "Variable",
            "readable": True,
            "namespace_index": 0 if node_id == "s=standard" else 2,
        }

    async def children(node_id):
        return ["s=standard"] if node_id == "ns=2;s=root" else []

    filtered = await discover_variables("ns=2;s=root", children, inspect)
    included = await discover_variables("ns=2;s=root", children, inspect, include_standard=True)
    assert len(filtered["nodes"]) == 1 and len(included["nodes"]) == 2

    async def inspect_object(node_id):
        return {"node_id": node_id, "node_class": "Object"}

    async def many_children(node_id):
        return [f"ns=2;i={index}" for index in range(10001)] if node_id == "i=85" else []

    bounded = await discover_variables("i=85", many_children, inspect_object)
    assert bounded["visited"] == 10000 and bounded["reason"] == "max_visited"


@pytest.mark.asyncio
async def test_discovery_rejects_results_after_connection_changes(monkeypatch):
    import src.proto.opcua.core.discovery as discovery
    from src.proto.opcua.core.transport import UaClientCore

    core = UaClientCore("opc.tcp://127.0.0.1:4840/ems/")
    monkeypatch.setattr(core, "_node", lambda _: object())
    monkeypatch.setattr(UaClientCore, "running", property(lambda _: True))

    async def reconnect_during_discovery(*args, **kwargs):
        core.generation += 1
        return {"nodes": []}

    monkeypatch.setattr(discovery, "discover_variables", reconnect_during_discovery)
    with pytest.raises(RuntimeError, match="连接已变化"):
        await core.discover_nodes()


@pytest.mark.asyncio
async def test_loopback_discovers_nested_nodes_and_subscribes_by_namespace_uri(monkeypatch):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = UaServerCore("127.0.0.1", port, "urn:ems:discovery")
    client = OpcUaClient(server.endpoint_url)
    try:
        await server.start()
        sdk = server._server
        folder = await sdk.nodes.objects.add_object("ns=2;s=folder", "Plant")
        variable = await folder.add_variable("ns=2;s=value", "Power", ua.Variant(12.5, ua.VariantType.Double))
        await variable.set_writable()
        hidden = await folder.add_variable("ns=2;s=hidden", "Hidden", 0)
        await hidden.write_attribute(ua.AttributeIds.AccessLevel, ua.DataValue(ua.Variant(0, ua.VariantType.Byte)))
        await hidden.write_attribute(ua.AttributeIds.UserAccessLevel, ua.DataValue(ua.Variant(0, ua.VariantType.Byte)))
        # Repeated references and a genuine cycle must not create repeated results.
        await sdk.nodes.objects.add_reference(variable, ua.ObjectIds.Organizes)
        await folder.add_reference(sdk.nodes.objects, ua.ObjectIds.HasComponent)
        await client.start()
        handler = OpcUaClientHandler()
        handler.client = client
        handler._is_running = True
        monkeypatch.setattr(api, "_channel", lambda _: {"protocol_type": 7, "conn_type": 1})
        request = Request(
            {
                "type": "http",
                "app": SimpleNamespace(
                    state=SimpleNamespace(
                        device_controller=SimpleNamespace(
                            get_device_by_id=lambda _: SimpleNamespace(protocol_handler=handler)
                        )
                    )
                ),
            }
        )
        result = (await api.discover_nodes(api.DiscoveryRequest(channel_id=1), request)).data
        assert not result["errors"] and not result["truncated"]
        assert len(result["nodes"]) == 1
        node = result["nodes"][0]
        assert node["node_id"] == "ns=2;s=value"
        assert node["namespace_uri"] == "urn:ems:discovery"
        assert node["data_type"] == "Double" and node["readable"] and node["writable"]
        await client.configure_subscriptions(
            {
                "subscriptions": [
                    {
                        "id": "discovered",
                        "items": [{"node_id": node["node_id"], "namespace_uri": node["namespace_uri"]}],
                    }
                ]
            }
        )
        async with asyncio.timeout(5):
            while not any(event.get("node_id") == node["node_id"] for event in client.stream.page()["events"]):
                await asyncio.sleep(0.05)
        direct = await client.discover_nodes(node["node_id"])
        assert len(direct["nodes"]) == 1
        with pytest.raises(ValidationError):
            await api.discover_nodes(api.DiscoveryRequest(channel_id=1, node_id="invalid"), request)
        await client.stop()
        with pytest.raises(OperationError):
            await api.discover_nodes(api.DiscoveryRequest(channel_id=1), request)
    finally:
        await client.stop()
        await server.stop()


def test_discovery_request_rejects_unbounded_parameters():
    from pydantic import ValidationError as ModelError

    for options in ({"max_depth": 65}, {"max_nodes": 1001}, {"timeout_s": 61}, {"node_id": ""}):
        with pytest.raises(ModelError):
            api.DiscoveryRequest(channel_id=1, **options)
