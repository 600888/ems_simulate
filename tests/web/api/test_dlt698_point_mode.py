"""DLT698 point-table selection retains existing values and imports typed definitions."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data.model.base import Base
from src.data.model.channel import Channel
from src.data.service import dlt698_service
from src.data.service.dlt698_service import Dlt698Service
from src.proto.dlt698.schema import Data, Point
from src.web.api.schemas.channel import ChannelCreateRequest, ChannelUpdateRequest


def test_dlt698_point_mode_request_validation():
    assert (
        ChannelCreateRequest(code="meter", name="meter", dlt698_point_mode="standard").dlt698_point_mode == "standard"
    )
    assert ChannelUpdateRequest(channel_id=7, dlt698_point_mode="import").dlt698_point_mode == "import"
    assert ChannelUpdateRequest(channel_id=7).dlt698_point_mode is None
    with pytest.raises(ValidationError):
        ChannelCreateRequest(code="meter", name="meter", dlt698_point_mode="unknown")


def test_standard_table_import_is_idempotent_and_preserves_existing_oad_aliases(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(dlt698_service, "local_session", sessions)
    with sessions() as session, session.begin():
        session.add(Channel(id=7, code="meter", name="meter", protocol_type=8, conn_type=2))
    original = Point(
        code="frequency",
        name="现场频率",
        oad="200F0200",
        data_type="UInt16",
        initial_value=Data(type="UInt16", value="4998"),
    )
    Dlt698Service.save_points(7, [original])
    count = Dlt698Service.import_standard_points(7)
    assert count > 0
    rows = Dlt698Service.points(7)
    frequency = [row for row in rows if row["oad"] == "200F0200"]
    assert len(frequency) == 1
    assert frequency[0]["code"] == "frequency"
    assert frequency[0]["initial_value"]["value"] == "4998"
    assert Dlt698Service.import_standard_points(7) == 0
    Dlt698Service.update_limits(7, "frequency", 45, 55)
    assert next(row for row in Dlt698Service.points(7) if row["code"] == "frequency")["max_value_limit"] == 55
    engine.dispose()


def test_metadata_edit_keeps_runtime_history_and_publication():
    from src.web.api.dlt698.router import persist_points
    from tests.protocols.dlt698.test_point_management import definition, make_device

    previous = definition()
    device = make_device([previous])
    runtime = device.protocol_handler.get_runtime()
    state = runtime.point_states["frequency"]
    state.enable_change_tracking()
    assert state.set_real_value(49.98)
    changed = {**deepcopy(previous), "name": "新名称"}
    with (
        patch("src.web.api.dlt698.router.get_handler", new=AsyncMock(return_value=device.protocol_handler)),
        patch.object(Dlt698Service, "points", return_value=[previous]),
        patch.object(Dlt698Service, "save_points", return_value=[changed]),
        patch("src.web.api.dlt698.router.refresh", new=AsyncMock()) as refresh,
    ):
        asyncio.run(persist_points(7, [Point.model_validate(changed)], SimpleNamespace(), "frequency"))
    refresh.assert_not_awaited()
    assert state.name == "新名称"
    assert state.real_value == 49.98
    assert len(state.change_history) == 1
