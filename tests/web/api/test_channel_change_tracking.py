import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, text

from src.data.controller.db_controller import DbController
from src.device.core.point.point_manager import PointManager
from src.device.factory.general_device_builder import GeneralDeviceBuilder
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yc, Yk, Yt, Yx
from src.web.api.channel.router import update_channel
from src.web.api.schemas.channel import ChannelCreateRequest, ChannelUpdateRequest


def test_history_defaults_off_and_applies_to_all_point_types_and_new_imports():
    assert ChannelCreateRequest(code="test", name="test").change_tracking_enabled is False
    manager = PointManager()
    points = [kind(code=f"p{index}") for index, kind in enumerate((Yc, Yx, Yk, Yt))]
    for slave_id, point in enumerate(points, 1):
        assert point.change_tracking_enabled is False
        manager.add_point(slave_id, point)
    points[0].value = 1
    assert points[0].change_history == []

    manager.set_change_tracking_enabled(True)
    assert all(point.change_tracking_enabled for point in points)
    points[0].value = 2
    assert len(points[0].change_history) == 1
    imported = Yc(code="imported")
    manager.add_point(1, imported)
    assert imported.change_tracking_enabled is True

    manager.set_change_tracking_enabled(False)
    assert not any(point.change_tracking_enabled for point in manager.get_all_points())
    points[0].value = 3
    assert len(points[0].change_history) == 1
    later = Yx(code="later")
    manager.add_point(2, later)
    assert later.change_tracking_enabled is False


@pytest.mark.parametrize("enabled", [True, False])
def test_device_save_updates_every_point_even_when_saved_setting_is_unchanged(enabled):
    manager = PointManager()
    manager.add_point(1, Yc(code="point"))
    manager.set_change_tracking_enabled(not enabled)
    device = SimpleNamespace(point_manager=manager)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                device_controller=SimpleNamespace(get_device_by_id=lambda _id: device),
            )
        )
    )
    existing = {
        "id": 1,
        "protocol_type": 1,
        "conn_type": 2,
        "dlt645_point_mode": "import",
        "change_tracking_enabled": enabled,
    }
    with (
        patch("src.web.api.channel.router.ChannelService.get_channel_by_id", return_value=existing),
        patch("src.web.api.channel.router.ChannelService.update_channel", return_value=True),
        patch("src.web.api.channel.router.reload_device_instance", new_callable=AsyncMock) as reload_device,
    ):
        asyncio.run(update_channel(ChannelUpdateRequest(channel_id=1, change_tracking_enabled=enabled), request))
    assert manager.change_tracking_enabled is enabled
    assert manager.get_all_points()[0].change_tracking_enabled is enabled
    reload_device.assert_not_called()


def test_legacy_migration_defaults_off_and_preserves_saved_choice():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE channel (id INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO channel (id) VALUES (1)"))
    controller = DbController()
    controller.db_config = SimpleNamespace(engine=engine)
    controller._migrate_channel_change_tracking_schema()
    with engine.begin() as conn:
        assert conn.scalar(text("SELECT change_tracking_enabled FROM channel WHERE id=1")) == 0
        conn.execute(text("UPDATE channel SET change_tracking_enabled=1 WHERE id=1"))
    controller._migrate_channel_change_tracking_schema()
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT change_tracking_enabled FROM channel WHERE id=1")) == 1
    engine.dispose()


@pytest.mark.parametrize("enabled", [True, False])
def test_rebuilt_iec61850_device_applies_saved_choice_to_discovered_points(enabled):
    builder = GeneralDeviceBuilder(channel_id=1)
    with (
        patch(
            "src.device.factory.general_device_builder.ChannelService.get_channel_by_id",
            return_value={"change_tracking_enabled": enabled},
        ),
        patch.object(builder, "initIec61850Client"),
    ):
        device = builder.makeGeneralDevice(1, "test", ProtocolType.Iec61850Client, False)
    point = Yc(code="discovered")
    device.point_manager.add_point(1, point)
    assert point.change_tracking_enabled is enabled
