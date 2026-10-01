"""OPC UA upload route contract without an HTTP test dependency."""

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from fastapi import Request, UploadFile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.data.model.channel import Channel
from src.data.model.opcua_config import OpcUaConfig
from src.data.model.opcua_feature import OpcUaFeature
from src.data.model.opcua_node import OpcUaNode
from src.data.model.opcua_point import OpcUaPoint
from src.data.model.opcua_secret import OpcUaSecret
import src.data.service.opcua_config_service as config_module
import src.data.service.opcua_point_import as import_module
from src.proto.opcua.point_excel import parse_point_excel
from src.web.api.exceptions import ValidationError
import src.web.api.opcua.router as api_module

TEMPLATE = Path(__file__).parents[3] / "data/point_csv/point_sample_opcua.xlsx"


@pytest.fixture
def isolated_routes(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Channel.metadata.create_all(
        engine,
        tables=[
            Channel.__table__,
            OpcUaConfig.__table__,
            OpcUaNode.__table__,
            OpcUaPoint.__table__,
            OpcUaFeature.__table__,
            OpcUaSecret.__table__,
        ],
    )
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(import_module, "local_session", sessions)
    monkeypatch.setattr(config_module, "local_session", sessions)
    monkeypatch.setattr(
        api_module,
        "_channel",
        lambda channel_id: {
            "id": channel_id,
            "protocol_type": 7,
            "conn_type": 2,
        },
    )
    with sessions() as session, session.begin():
        session.add(
            Channel(id=2, code="UA_SERVER", name="UA server", protocol_type=7, conn_type=2, ip="127.0.0.1", port=4840)
        )
    app = SimpleNamespace(
        state=SimpleNamespace(
            device_controller=SimpleNamespace(
                get_device_by_id=lambda _channel_id: None,
            )
        )
    )
    yield Request({"type": "http", "app": app})
    engine.dispose()


def upload(content: bytes) -> UploadFile:
    return UploadFile(file=BytesIO(content), filename="points.xlsx")


@pytest.mark.asyncio
async def test_point_upload_preview_apply_list_delete(isolated_routes):
    content = TEMPLATE.read_bytes()
    inspection = (await api_module.preview_points(channel_id=2, file=upload(content))).data
    assert inspection["total"] == 27 and not inspection["errors"]

    result = (
        await api_module.apply_points(
            isolated_routes,
            channel_id=2,
            expected_sha256=inspection["sha256"],
            mode="add",
            file=upload(content),
        )
    ).data
    assert result["created"] == 27

    listed = (await api_module.list_points(api_module.PointListRequest(channel_id=2, limit=5))).data
    assert listed["total"] == 27 and len(listed["points"]) == 5
    exported = await api_module.export_points(api_module.ChannelRequest(channel_id=2))
    assert exported.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert len(parse_point_excel(exported.body).rows) == 27

    with pytest.raises(ValidationError) as conflict:
        await api_module.apply_points(
            isolated_routes,
            channel_id=2,
            expected_sha256=inspection["sha256"],
            mode="add",
            file=upload(content),
        )
    assert len(conflict.value.data["conflicts"]) == 27

    code = listed["points"][0]["point_code"]
    deleted = await api_module.delete_point(
        api_module.PointDeleteRequest(channel_id=2, point_code=code),
        isolated_routes,
    )
    assert deleted.data == {"deleted": True}
    cleared = await api_module.clear_points(api_module.ChannelRequest(channel_id=2), isolated_routes)
    assert cleared.data == {"deleted": 26}
    assert (await api_module.list_points(api_module.PointListRequest(channel_id=2))).data["total"] == 0
