"""Command workflow persistence, API compatibility and live reconfiguration."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import c104
from pydantic import ValidationError
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.data.controller.db_controller import DbController
import src.data.dao.point_dao as point_dao_module
from src.data.dao.point_dao import PointDao
from src.data.model import Base
from src.data.service.yk_service import YkService
from src.data.service.yt_service import YtService
from src.device.core.point.point_operator import PointOperator
from src.device.protocol.iec104_handler import IEC104ClientHandler, IEC104ServerHandler
from src.device.simulator.simulation_controller import SimulationController
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import SimulateMethod, Yc, Yk, Yt
from src.proto.iec104.iec104client import IEC104Client
from src.proto.iec104.iec104server import IEC104Server
from src.web.api.point.router import edit_iec104_metadata
from src.web.api.schemas.point import Iec104MetadataEditRequest, PointCreateRequest, PointItem, PointMetadataEditRequest


@pytest.fixture
def database(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(point_dao_module, "local_session", sessionmaker(engine, expire_on_commit=False))
    yield engine
    engine.dispose()


@pytest.mark.parametrize("frame_type,service", [(2, YkService), (3, YtService)])
def test_command_mode_survives_create_batch_edit_and_reload(database, frame_type, service):
    data = {"code": "CMD", "name": "Command", "reg_addr": "100", "iec_command_mode": "SELECT_AND_EXECUTE"}
    saved = PointDao.create_point(1, frame_type, data)
    assert saved["iec_command_mode"] == "SELECT_AND_EXECUTE"
    loaded = service._create_point(PointDao.get_point_by_code("CMD", 1), ProtocolType.Iec104Server)
    assert loaded.iec_command_mode == "SELECT_AND_EXECUTE"

    assert PointDao.update_point_metadata("CMD", {"iec_command_mode": "DIRECT"}, 1)
    loaded = service._create_point(PointDao.get_point_by_code("CMD", 1), ProtocolType.Iec104Server)
    assert loaded.iec_command_mode == "DIRECT"

    batch = PointDao.create_points_batch(
        1,
        frame_type,
        [
            {**data, "code": "BATCH"},
            {"code": "LEGACY", "name": "Legacy", "reg_addr": "101"},
        ],
    )
    assert [point["iec_command_mode"] for point in batch] == ["SELECT_AND_EXECUTE", "DIRECT"]


def test_legacy_schema_upgrade_preserves_rows_and_is_repeatable():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        for table in ("point_yk", "point_yt"):
            connection.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, code TEXT)"))
            connection.execute(text(f"INSERT INTO {table} VALUES (1, 'existing')"))
    controller = DbController()
    controller.db_config = SimpleNamespace(engine=engine)
    controller._migrate_iec104_command_mode_schema()
    controller._migrate_iec104_command_mode_schema()
    with engine.connect() as connection:
        for table in ("point_yk", "point_yt"):
            assert connection.execute(text(f"SELECT code, iec_command_mode FROM {table}")).one() == (
                "existing",
                "DIRECT",
            )
    engine.dispose()


def test_api_validates_modes_and_keeps_legacy_edits_compatible():
    common = {"device_name": "D", "point_code": "CMD"}
    assert Iec104MetadataEditRequest(**common).iec_command_mode is None
    with pytest.raises(ValidationError):
        Iec104MetadataEditRequest(**common, iec_command_mode="AUTO")
    with pytest.raises(ValidationError):
        PointMetadataEditRequest(**common, metadata={"decode_code": "UINT16_AB", "iec_command_mode": "AUTO"})
    create = {"code": "C", "name": "C", "reg_addr": "1"}
    assert PointCreateRequest(device_name="D", frame_type=2, **create).iec_command_mode == "DIRECT"
    assert PointItem(**create, iec_command_mode="SELECT_AND_EXECUTE").iec_command_mode == "SELECT_AND_EXECUTE"

    device = SimpleNamespace(protocol_type=ProtocolType.Iec104Server, edit_point_metadata=Mock(return_value=True))
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                device_controller=SimpleNamespace(device_map={"D": device}),
            )
        )
    )
    asyncio.run(edit_iec104_metadata(Iec104MetadataEditRequest(**common), request))
    assert "iec_command_mode" not in device.edit_point_metadata.call_args.args[1]
    asyncio.run(
        edit_iec104_metadata(
            Iec104MetadataEditRequest(**common, iec_command_mode="SELECT_AND_EXECUTE"),
            request,
        )
    )
    assert device.edit_point_metadata.call_args.args[1]["iec_command_mode"] == "SELECT_AND_EXECUTE"


@pytest.mark.parametrize("point_class,type_id", [(Yk, "C_SC_NA_1"), (Yt, "C_SE_NC_1")])
@pytest.mark.parametrize("client", [False, True])
def test_saved_mode_applies_to_created_point_and_live_edit_without_sending(monkeypatch, point_class, type_id, client):
    protocol = ProtocolType.Iec104Client if client else ProtocolType.Iec104Server
    handler = IEC104ClientHandler() if client else IEC104ServerHandler()
    if client:
        native = IEC104Client(ip="127.0.0.1", port=2404)
        handler._client = native
    else:
        native = IEC104Server(ip="127.0.0.1", port=0)
        handler._server = native
    point = point_class(code="CMD", address="0x0064", iec_type_id=type_id, iec_command_mode="SELECT_AND_EXECUTE")
    handler.add_points([point])
    command = native.stations[1].get_point(io_address=100)
    assert command.command_mode == c104.CommandMode.SELECT_AND_EXECUTE

    # A second station with the same IOA must retain its own mode.
    other = point_class(code="OTHER", rtu_addr="2", address="0x0064", iec_type_id=type_id)
    handler.add_points([other])
    device = SimpleNamespace(
        name="D",
        protocol_type=protocol,
        protocol_handler=handler,
        point_manager=SimpleNamespace(get_point_by_code=lambda _code: point),
        log=Mock(),
    )
    operator = PointOperator(device)
    monkeypatch.setattr(operator, "_get_channel_id", lambda: 1)
    save = Mock(return_value=True)
    monkeypatch.setattr("src.device.core.point.point_operator.PointService.update_point_metadata", save)
    monkeypatch.setattr(handler, "write_value", Mock())

    assert operator.edit_metadata("CMD", {"iec_command_mode": "DIRECT", "iec_type_id": type_id, "iec_quality": 0})
    assert point.iec_command_mode == "DIRECT"
    assert command.command_mode == c104.CommandMode.DIRECT
    assert operator.edit_metadata("CMD", {"iec_command_mode": "SELECT_AND_EXECUTE"})
    assert command.command_mode == c104.CommandMode.SELECT_AND_EXECUTE
    assert native.stations[2].get_point(io_address=100).command_mode == c104.CommandMode.DIRECT
    handler.write_value.assert_not_called()

    # Failed persistence must not alter the currently active workflow.
    save.return_value = False
    assert not operator.edit_metadata("CMD", {"iec_command_mode": "DIRECT"})
    assert command.command_mode == c104.CommandMode.SELECT_AND_EXECUTE
    assert point.iec_command_mode == "SELECT_AND_EXECUTE"

    controller = SimulationController(device)
    controller.add_point(point, SimulateMethod.Random, 1)
    assert controller.get_point_info("CMD")["iec_command_mode"] == "SELECT_AND_EXECUTE"


def test_monitoring_point_rejects_command_mode_before_mutation():
    point = Yc(code="YC", name="Original")
    device = SimpleNamespace(
        name="D",
        protocol_type=ProtocolType.Iec104Server,
        protocol_handler=None,
        point_manager=SimpleNamespace(get_point_by_code=lambda _code: point),
        log=Mock(),
    )
    with pytest.raises(ValueError, match="IEC104"):
        PointOperator(device).edit_metadata("YC", {"name": "Changed", "iec_command_mode": "SELECT_AND_EXECUTE"})
    assert point.name == "Original"
