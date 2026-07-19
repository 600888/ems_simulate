"""Device-group hard deletion regression tests."""

from unittest.mock import call, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.data.dao.device_group_dao as device_group_dao_module
from src.data.dao.device_group_dao import DeviceGroupDao
import src.data.model  # noqa: F401
from src.data.model.base import Base
from src.data.model.device import Device
from src.data.model.device_group import DeviceGroup
from src.data.service.device_group_service import DeviceGroupService


def _session_factory(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(device_group_dao_module, "local_session", factory)
    return factory


def test_non_cascade_delete_is_hard_delete_and_releases_group_code(monkeypatch):
    factory = _session_factory(monkeypatch)
    with factory() as session, session.begin():
        parent = DeviceGroup(code="PARENT", name="Parent")
        session.add(parent)
        session.flush()
        session.add_all(
            [
                DeviceGroup(code="CHILD", name="Child", parent_id=parent.id),
                Device(code="DEVICE", name="Device", group_id=parent.id),
            ]
        )
        parent_id = parent.id

    assert DeviceGroupDao.delete_group(parent_id, cascade=False) is True

    with factory() as session:
        assert session.get(DeviceGroup, parent_id) is None
        assert session.query(DeviceGroup).where(DeviceGroup.code == "CHILD").one().parent_id is None
        assert session.query(Device).where(Device.code == "DEVICE").one().group_id is None

    recreated_id = DeviceGroupDao.create_group("PARENT", "Parent recreated")
    assert recreated_id > 0


def test_cascade_delete_hard_deletes_descendant_groups_and_devices(monkeypatch):
    factory = _session_factory(monkeypatch)
    with factory() as session, session.begin():
        root = DeviceGroup(code="ROOT", name="Root")
        session.add(root)
        session.flush()
        child = DeviceGroup(code="CHILD", name="Child", parent_id=root.id)
        session.add(child)
        session.flush()
        session.add_all(
            [
                Device(code="ROOT_DEVICE", name="Root device", group_id=root.id),
                Device(code="CHILD_DEVICE", name="Child device", group_id=child.id),
            ]
        )
        root_id = root.id

    assert DeviceGroupDao.delete_group(root_id, cascade=True) is True

    with factory() as session:
        assert session.query(DeviceGroup).count() == 0
        assert session.query(Device).count() == 0


def test_cascade_delete_cleans_each_channel_before_deleting_groups():
    with (
        patch.object(DeviceGroupDao, "get_channel_ids_for_group_tree", return_value=[11, 12]),
        patch.object(DeviceGroupDao, "delete_group", return_value=True) as delete_group,
        patch("src.data.service.device_group_service.ChannelConfigurationService.delete_for_channel") as delete_config,
        patch("src.data.service.device_group_service.ChannelService.delete_channel") as delete_channel,
    ):
        assert DeviceGroupService.delete_group(5, cascade=True) is True

    assert delete_config.call_args_list == [call(11), call(12)]
    assert delete_channel.call_args_list == [call(11), call(12)]
    delete_group.assert_called_once_with(5, True)
