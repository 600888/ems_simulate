"""OPC UA workbook validation and transactional point import."""

from io import BytesIO
from pathlib import Path
import socket

from asyncua import ua
from openpyxl import load_workbook
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from src.data.model.channel import Channel
from src.data.model.opcua_config import OpcUaConfig
from src.data.model.opcua_node import OpcUaNode
from src.data.model.opcua_point import OpcUaPoint
import src.data.service.opcua_point_import as import_module
from src.proto.opcua.core.transport import UaClientCore, UaServerCore
from src.proto.opcua.point_excel import parse_point_excel

TEMPLATE = Path(__file__).parents[3] / "data/point_csv/point_sample_opcua.xlsx"


@pytest.fixture
def isolated_db(monkeypatch):
    engine = create_engine("sqlite://")
    Channel.metadata.create_all(
        engine,
        tables=[
            Channel.__table__,
            OpcUaConfig.__table__,
            OpcUaNode.__table__,
            OpcUaPoint.__table__,
        ],
    )
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(import_module, "local_session", sessions)
    with sessions() as session, session.begin():
        session.add_all(
            [
                Channel(
                    id=1, code="UA_CLIENT", name="UA client", protocol_type=7, conn_type=1, ip="127.0.0.1", port=4840
                ),
                Channel(
                    id=2, code="UA_SERVER", name="UA server", protocol_type=7, conn_type=2, ip="127.0.0.1", port=4841
                ),
            ]
        )
    yield sessions
    engine.dispose()


def edited_workbook(sheet_name: str, cell: str, value) -> bytes:
    workbook = load_workbook(TEMPLATE)
    if value == "__DUPLICATE_FIRST__":
        value = workbook[sheet_name]["A2"].value
    workbook[sheet_name][cell] = value
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()
    return stream.getvalue()


def test_template_preview_and_server_import(isolated_db):
    content = TEMPLATE.read_bytes()
    inspection = import_module.OpcUaPointImportService.preview(2, content)
    assert inspection.to_dict()["counts"] == {"遥测": 13, "遥信": 7, "遥控": 3, "遥调": 4}
    assert not inspection.errors and not inspection.conflicts

    result = import_module.OpcUaPointImportService.apply(2, content, inspection.parsed.sha256, "add")
    assert result["created"] == 27 and result["updated"] == 0
    with isolated_db() as session:
        assert session.scalar(select(func.count()).select_from(OpcUaPoint)) == 27
        assert session.scalar(select(func.count()).select_from(OpcUaNode)) == 27
        assert session.get(OpcUaConfig, 2).namespace_uri == "urn:ems:simulate:bess"
    listed = import_module.OpcUaPointImportService.list_points(2, point_type=0, limit=5)
    assert listed["total"] == 13 and len(listed["points"]) == 5
    assert import_module.OpcUaPointImportService.has_points(2)
    exported = parse_point_excel(import_module.OpcUaPointImportService.export(2))
    assert not exported.errors and len(exported.rows) == 27
    actual = {
        row["point_code"]: {key: value for key, value in row.items() if key != "excel_row"} for row in exported.rows
    }
    expected = {
        row["point_code"]: {key: value for key, value in row.items() if key != "excel_row"}
        for row in inspection.parsed.rows
    }
    assert actual == expected


@pytest.mark.parametrize("channel_id", [1, 2])
def test_clear_points_preserves_standalone_nodes(isolated_db, channel_id):
    content = TEMPLATE.read_bytes()
    service = import_module.OpcUaPointImportService
    digest = service.preview(channel_id, content).parsed.sha256
    service.apply(channel_id, content, digest, "add")
    with isolated_db() as session, session.begin():
        session.add(
            OpcUaNode(
                channel_id=channel_id,
                node_id="ns=2;s=standalone",
                namespace_uri="urn:ems:simulate:bess",
                browse_name="Standalone",
                data_type="Double",
                initial_value=0.0,
                writable=False,
            )
        )
    assert service.clear(channel_id) == {"deleted": 27}
    assert not service.has_points(channel_id)
    with isolated_db() as session:
        assert session.scalars(select(OpcUaNode.node_id)).all() == ["ns=2;s=standalone"]
    assert service.clear(channel_id) == {"deleted": 0}


def test_client_import_only_creates_local_points(isolated_db):
    content = TEMPLATE.read_bytes()
    digest = import_module.OpcUaPointImportService.preview(1, content).parsed.sha256
    result = import_module.OpcUaPointImportService.apply(1, content, digest, "add")
    assert result["role"] == "client" and result["created"] == 27
    with isolated_db() as session:
        assert session.scalar(select(func.count()).select_from(OpcUaPoint)) == 27
        assert session.scalar(select(func.count()).select_from(OpcUaNode)) == 0


@pytest.mark.parametrize(
    "sheet,cell,value,field",
    [
        ("遥测", "A3", "__DUPLICATE_FIRST__", "测点编码"),
        ("遥测", "D2", "bad-node-id", "NodeId"),
        ("遥控", "J2", "MISSING_SIGNAL", "关联遥信编码"),
    ],
)
def test_row_errors_prevent_any_write(isolated_db, sheet, cell, value, field):
    content = edited_workbook(sheet, cell, value)
    inspection = import_module.OpcUaPointImportService.preview(2, content)
    assert any(error.field == field for error in inspection.errors)
    with pytest.raises(import_module.PointImportError) as error:
        import_module.OpcUaPointImportService.apply(2, content, inspection.parsed.sha256, "add")
    assert any(item.field == field for item in error.value.errors)
    with isolated_db() as session:
        assert session.scalar(select(func.count()).select_from(OpcUaPoint)) == 0
        assert session.scalar(select(func.count()).select_from(OpcUaNode)) == 0


def test_add_conflict_then_explicit_overwrite(isolated_db):
    content = TEMPLATE.read_bytes()
    digest = import_module.OpcUaPointImportService.preview(2, content).parsed.sha256
    import_module.OpcUaPointImportService.apply(2, content, digest, "add")
    inspection = import_module.OpcUaPointImportService.preview(2, content)
    assert len(inspection.conflicts) == 27
    with pytest.raises(import_module.PointImportError, match="冲突"):
        import_module.OpcUaPointImportService.apply(2, content, digest, "add")
    result = import_module.OpcUaPointImportService.apply(2, content, digest, "overwrite")
    assert result["created"] == 0 and result["updated"] == 27
    with isolated_db() as session:
        assert session.scalar(select(func.count()).select_from(OpcUaPoint)) == 27


def test_file_digest_must_match_preview(isolated_db):
    with pytest.raises(import_module.PointImportError, match="重新预检"):
        import_module.OpcUaPointImportService.apply(2, TEMPLATE.read_bytes(), "wrong", "add")
    with isolated_db() as session:
        assert session.scalar(select(func.count()).select_from(OpcUaPoint)) == 0


@pytest.mark.asyncio
async def test_imported_server_nodes_can_be_browsed_and_written(isolated_db):
    content = TEMPLATE.read_bytes()
    digest = import_module.OpcUaPointImportService.preview(2, content).parsed.sha256
    import_module.OpcUaPointImportService.apply(2, content, digest, "add")
    with isolated_db() as session:
        definitions = [
            {
                "node_id": row.node_id,
                "browse_name": row.browse_name,
                "data_type": row.data_type,
                "initial_value": row.initial_value,
                "writable": row.writable,
            }
            for row in session.scalars(select(OpcUaNode)).all()
        ]
        control_id = session.scalar(select(OpcUaPoint.node_id).where(OpcUaPoint.point_type == 2).limit(1))
        telemetry_id = session.scalar(select(OpcUaPoint.node_id).where(OpcUaPoint.point_type == 0).limit(1))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = UaServerCore("127.0.0.1", port, "urn:ems:simulate:bess", definitions=definitions)
    client = UaClientCore(server.endpoint_url)
    try:
        await server.start()
        await client.start()
        nodes = await client.browse(limit=100)
        assert len([item for item in nodes if item["node_id"].startswith("ns=2;s=")]) == 27
        assert any(item["node_id"] == control_id for item in nodes)
        assert (await client.write(control_id, True))["value"] is True
        with pytest.raises(ua.UaStatusCodeError):
            await client.write(telemetry_id, 1.0)
    finally:
        await client.stop()
        await server.stop()
