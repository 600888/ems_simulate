"""Live configuration uses real UA sessions and rolls back rejected updates."""

import asyncio
from datetime import UTC, datetime, timedelta
import importlib
from io import BytesIO
import socket
from types import SimpleNamespace

from asyncua import ua
from fastapi import Request, UploadFile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.data.model.channel import Channel
from src.data.service.opcua_feature_service import OpcUaFeatureService
from src.data.service.opcua_live_service import OpcUaLiveService
from src.data.service.opcua_node_service import OpcUaNodeService
from src.device.protocol.opcua_handler import OpcUaServerHandler
from src.proto.opcua.client import OpcUaClient
from src.proto.opcua.point_excel import export_point_excel
from src.proto.opcua.server import OpcUaServer
from src.web.api.exceptions import ValidationError
import src.web.api.opcua.router as api

NODE = "ns=2;s=power"
URI = "urn:ems-simulate:channel:2"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def definition(**changes):
    return dict(node_id=NODE, browse_name="Power", data_type="Double", initial_value=0.0, writable=True, **changes)


async def wait_value(client, value):
    async with asyncio.timeout(5):
        while (await client.read(NODE))["value"] != value:
            await asyncio.sleep(0.05)


@pytest.fixture
def online_routes(monkeypatch, tmp_path):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Channel.metadata.create_all(
        engine, tables=[Channel.__table__, *(model.__table__ for model in OpcUaLiveService.MODELS)]
    )
    sessions = sessionmaker(engine, expire_on_commit=False)
    for suffix in (
        "config_service",
        "feature_service",
        "live_service",
        "node_service",
        "point_import",
        "security_service",
        "model_service",
    ):
        monkeypatch.setattr(importlib.import_module(f"src.data.service.opcua_{suffix}"), "local_session", sessions)
    monkeypatch.setattr(api, "_channel", lambda channel_id: {"id": channel_id, "protocol_type": 7, "conn_type": 2})
    with sessions() as session, session.begin():
        session.add(Channel(id=2, code="UA", name="UA", protocol_type=7, conn_type=2, ip="127.0.0.1", port=free_port()))
    OpcUaNodeService.upsert_variable(2, URI, definition())
    server = OpcUaServer(
        "127.0.0.1",
        free_port(),
        URI,
        definitions=OpcUaNodeService.list_nodes(2),
        features={"history_path": str(tmp_path / "history.sqlite")},
    )
    handler = OpcUaServerHandler()
    handler.server = server
    handler._is_running = True
    device = SimpleNamespace(protocol_handler=handler)
    app = SimpleNamespace(state=SimpleNamespace(device_controller=SimpleNamespace(get_device_by_id=lambda _: device)))
    yield Request({"type": "http", "app": app}), server
    engine.dispose()


async def save(request, name, config):
    return await api.save_feature(api.FeatureRequest(channel_id=2, name=name, config=config), request)


@pytest.mark.asyncio
async def test_online_rules_preserve_pause_and_session_and_rollback(online_routes):
    request, server = online_routes
    client = OpcUaClient(server.endpoint_url)
    try:
        await server.start()
        await client.start()
        transport, connection = server._core._server, client._core._client
        config = {
            "rules": [{"node_id": NODE, "kind": "fixed", "value": 3.0, "interval_ms": 50, "write_policy": "overwrite"}]
        }
        await save(request, "simulation", config)
        await wait_value(client, 3.0)
        origin = server._registry.feature("simulation")._origins[NODE]
        server.pause_simulation(True)
        config["rules"][0]["value"] = 8.0
        config["rules"][0]["write_policy"] = "reject"
        await save(request, "simulation", config)
        await asyncio.sleep(0.15)
        assert (await client.read(NODE))["value"] == 3.0
        assert server._registry.feature("simulation")._origins[NODE] == origin
        with pytest.raises(ua.UaStatusCodeError):
            await client.write(NODE, 99.0)
        server.pause_simulation(False)
        await wait_value(client, 8.0)
        before = OpcUaFeatureService.load(2)
        config["rules"][0]["value"] = "invalid double"
        with pytest.raises(ValidationError):
            await save(request, "simulation", config)
        assert OpcUaFeatureService.load(2) == before
        assert (await client.read(NODE))["value"] == 8.0
        await save(request, "simulation", {"rules": []})
        await client.write(NODE, 99.0)
        assert (await client.read(NODE))["value"] == 99.0
        assert server._core._server is transport and client._core._client is connection
    finally:
        await client.stop()
        await server.stop()


@pytest.mark.asyncio
async def test_online_nodes_permissions_defaults_and_type_boundary(online_routes):
    request, server = online_routes
    client = OpcUaClient(
        server.endpoint_url,
        features={
            "subscriptions": {
                "subscriptions": [{"id": "power", "publishing_interval_ms": 50, "items": [{"node_id": NODE}]}]
            }
        },
    )
    try:
        await server.start()
        await client.start()
        connection = client._core._client
        await client.write(NODE, 7.0)
        edited = {**definition(), "browse_name": "Renamed", "writable": False, "initial_value": 20.0}
        await api.upsert_variable(api.UpsertVariableRequest(channel_id=2, **edited), request)
        assert (await client.read(NODE))["value"] == 7.0
        assert (await connection.get_node(NODE).read_browse_name()).Name == "Renamed"
        with pytest.raises(ua.UaStatusCodeError):
            await client.write(NODE, 8.0)
        before = OpcUaNodeService.list_nodes(2)
        with pytest.raises(ValidationError, match="数据类型"):
            await api.upsert_variable(
                api.UpsertVariableRequest(channel_id=2, **{**edited, "data_type": "Int32", "initial_value": 1}), request
            )
        assert OpcUaNodeService.list_nodes(2) == before
        await server.reset_values()
        assert (await client.read(NODE))["value"] == 20.0
        added = {**definition(), "node_id": "ns=2;s=new", "initial_value": 11.0}
        await api.upsert_variable(api.UpsertVariableRequest(channel_id=2, **added), request)
        assert (await client.read(added["node_id"]))["value"] == 11.0
        await save(request, "simulation", {"rules": [{"node_id": added["node_id"], "kind": "fixed", "value": 4.0}]})
        await save(request, "history", {"enabled": True, "nodes": [added["node_id"]]})
        await api.delete_variable(api.NodeRequest(channel_id=2, node_id=added["node_id"]), request)
        assert OpcUaFeatureService.load(2)["simulation"]["rules"] == []
        assert OpcUaFeatureService.load(2)["history"]["nodes"] == []
        assert (await client.read(added["node_id"]))["status_code"] == "BadNodeIdUnknown"
        await api.upsert_variable(api.UpsertVariableRequest(channel_id=2, **{**edited, "writable": True}), request)
        await client.write(NODE, 33.0)
        async with asyncio.timeout(5):
            while not any(item.get("value") == 33.0 for item in client.stream.page()["events"]):
                await asyncio.sleep(0.05)
        assert client._core._client is connection
    finally:
        await client.stop()
        await server.stop()


@pytest.mark.asyncio
async def test_online_excel_import_overwrite_clear_and_nodeset_import(online_routes):
    request, server = online_routes
    client = OpcUaClient(server.endpoint_url)

    def upload(content, filename):
        return UploadFile(file=BytesIO(content), filename=filename)

    point = dict(
        point_type=0,
        point_code="IMPORT",
        point_name="Imported",
        attribute_code="imported",
        node_id="ns=2;s=imported",
        namespace_uri=URI,
        data_type="Double",
        sampling_interval_ms=1000,
        unit="kW",
        scale_mul=1,
        scale_add=0,
        upper_limit=100,
        lower_limit=0,
        initial_value=5.0,
    )
    try:
        await server.start()
        await client.start()
        connection, transport = client._core._client, server._core._server
        content = export_point_excel([point])
        inspection = (await api.preview_points(channel_id=2, file=upload(content, "points.xlsx"))).data
        assert not inspection["errors"]
        await api.apply_points(
            request, channel_id=2, expected_sha256=inspection["sha256"], mode="add", file=upload(content, "points.xlsx")
        )
        assert (await client.read(point["node_id"]))["value"] == 5.0
        content = export_point_excel([{**point, "point_name": "Updated", "initial_value": 10.0}])
        inspection = (await api.preview_points(channel_id=2, file=upload(content, "points.xlsx"))).data
        await api.apply_points(
            request,
            channel_id=2,
            expected_sha256=inspection["sha256"],
            mode="overwrite",
            file=upload(content, "points.xlsx"),
        )
        assert (await connection.get_node(point["node_id"]).read_browse_name()).Name == "Updated"
        assert (await client.read(point["node_id"]))["value"] == 5.0
        await api.clear_points(api.ChannelRequest(channel_id=2), request)
        assert (await client.read(point["node_id"]))["status_code"] == "BadNodeIdUnknown"
        assert (await client.read(NODE))["value"] == 0.0
        xml = (await server.export_nodeset()).replace(b"Power", b"ModelRenamed")
        inspection = (await api.preview_model(channel_id=2, file=upload(xml, "model.xml"))).data
        assert not inspection["errors"]
        await api.apply_model(
            request, channel_id=2, expected_sha256=inspection["sha256"], mode="overwrite", file=upload(xml, "model.xml")
        )
        assert (await connection.get_node(NODE).read_browse_name()).Name == "ModelRenamed"
        assert client._core._client is connection and server._core._server is transport
    finally:
        await client.stop()
        await server.stop()


@pytest.mark.asyncio
async def test_online_history_keeps_database_and_recovers_failed_update(online_routes):
    request, server = online_routes
    client = OpcUaClient(server.endpoint_url)
    start = datetime.now(UTC) - timedelta(minutes=1)
    try:
        await server.start()
        await client.start()
        await save(request, "history", {"enabled": True, "nodes": [NODE], "max_values": 100})
        storage = server._core._history_storage
        for value in (1.0, 2.0):
            await client.write(NODE, value)
            await asyncio.sleep(0.15)
        await save(request, "history", {"enabled": True, "nodes": [NODE], "max_values": 200, "retention_days": 5})
        before = OpcUaFeatureService.load(2)
        with pytest.raises(ValidationError):
            await save(request, "history", {"enabled": True, "nodes": ["ns=2;s=missing"]})
        assert OpcUaFeatureService.load(2) == before
        await client.write(NODE, 3.0)
        await asyncio.sleep(0.15)
        history = await client.read_history(NODE, start, datetime.now(UTC), 100)
        assert {1.0, 2.0, 3.0} <= {item["value"] for item in history["values"]}
        assert server._core._history_storage is storage
        await save(request, "history", {"enabled": False, "nodes": [NODE]})
        await client.write(NODE, 9.0)
        await asyncio.sleep(0.15)
        await save(request, "history", {"enabled": True, "nodes": [NODE]})
        history = await client.read_history(NODE, start, datetime.now(UTC), 100)
        assert {1.0, 2.0, 3.0} <= {item["value"] for item in history["values"]}
    finally:
        await client.stop()
        await server.stop()


@pytest.mark.asyncio
async def test_online_server_and_client_events_keep_connection(online_routes):
    request, server = online_routes
    client = OpcUaClient(server.endpoint_url)
    try:
        await server.start()
        await client.start()
        connection = client._core._client
        await save(request, "events", {"enabled": True})
        await client.configure_feature("events", {"enabled": True, "minimum_severity": 500})
        await server.emit_event("online", 750)
        async with asyncio.timeout(5):
            while not any(item.get("Message") == "online" for item in client.stream.page()["events"]):
                await asyncio.sleep(0.05)
        await client.configure_feature("events", {"enabled": False})
        await server.emit_event("disabled", 750)
        await asyncio.sleep(0.2)
        assert not any(item.get("Message") == "disabled" for item in client.stream.page()["events"])
        await save(request, "events", {"enabled": False})
        with pytest.raises(ValueError):
            await server.emit_event("disabled server", 750)
        assert client._core._client is connection
        assert (await client.read(NODE))["value"] == 0.0
    finally:
        await client.stop()
        await server.stop()


@pytest.mark.asyncio
async def test_node_apply_failure_restores_runtime_and_database(online_routes, monkeypatch):
    request, server = online_routes
    client = OpcUaClient(server.endpoint_url)
    try:
        await server.start()
        await client.start()
        await save(request, "history", {"enabled": True, "nodes": [NODE]})
        await client.write(NODE, 17.0)
        before = OpcUaLiveService.snapshot(2)
        original = server._core._install
        failed = False

        async def fail_once(transport, index, definitions):
            nonlocal failed
            await original(transport, index, definitions)
            if not failed:
                failed = True
                raise ValueError("injected node failure")

        monkeypatch.setattr(server._core, "_install", fail_once)
        added = {**definition(), "node_id": "ns=2;s=new"}
        history_plugin = server._registry.feature("history")
        simulation_plugin = server._registry.feature("simulation")
        with pytest.raises(ValidationError, match="injected node failure"):
            await api.upsert_variable(api.UpsertVariableRequest(channel_id=2, **added), request)
        assert OpcUaLiveService.snapshot(2) == before
        assert (await client.read(NODE))["value"] == 17.0
        assert (await client.read(added["node_id"]))["status_code"] == "BadNodeIdUnknown"
        assert server.node_count == 1
        assert server._registry.feature("history") is history_plugin
        assert server._registry.feature("simulation") is simulation_plugin
        assert all(item["running"] for item in server.capabilities())
    finally:
        await client.stop()
        await server.stop()
