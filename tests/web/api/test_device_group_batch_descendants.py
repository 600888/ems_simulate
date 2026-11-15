from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.data.dao.device_group_dao as dao_module
from src.data.dao.device_group_dao import DeviceGroupDao
from src.data.model import Base, Device, DeviceGroup
from src.enums.modbus_def import ProtocolType
from src.web.api.device_group.router import batch_device_operation
from src.web.api.schemas import BatchDeviceOperationRequest


@pytest.fixture
def group_devices(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(dao_module, "local_session", factory)
    with factory() as session, session.begin():
        session.add_all(
            DeviceGroup(id=group_id, code=f"G{group_id}", name=f"group-{group_id}", parent_id=parent_id)
            for group_id, parent_id in [(1, None), (2, 1), (3, 2), (4, 1), (5, None)]
        )
        session.add_all(
            Device(id=device_id, code=f"D{device_id}", name=f"device-{device_id}", group_id=group_id, enable=enabled)
            for device_id, group_id, enabled in [
                (2, 2, True),
                (3, 3, True),
                (4, 4, True),
                (5, 5, True),
                (6, None, True),
                (7, 3, False),
            ]
        )
    devices = {
        f"device-{device_id}": SimpleNamespace(
            name=f"device-{device_id}",
            protocol_type=ProtocolType.ModbusTcpServer,
            start=AsyncMock(return_value=True),
            stop=AsyncMock(return_value=True),
        )
        for device_id in range(2, 8)
    }
    yield devices
    engine.dispose()


def test_group_query_defaults_to_direct_devices_and_can_include_all_descendants(group_devices):
    assert [d["id"] for d in DeviceGroupDao.get_devices_by_group(2)] == [2]
    assert [d["id"] for d in DeviceGroupDao.get_devices_by_group(1, include_descendants=True)] == [2, 3, 4]
    assert [d["id"] for d in DeviceGroupDao.get_devices_by_group(2, include_descendants=True)] == [2, 3]
    assert DeviceGroupDao.get_devices_by_group(999, include_descendants=True) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["start", "stop"])
@pytest.mark.parametrize("group_id, expected_ids", [(1, [2, 3, 4]), (2, [2, 3]), (0, [6])])
async def test_sidebar_batch_includes_descendants_and_excludes_other_groups(
    group_devices, operation, group_id, expected_ids
):
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(device_controller=SimpleNamespace(device_map=group_devices)))
    )
    response = await batch_device_operation(
        BatchDeviceOperationRequest(group_id=group_id, operation=operation), request
    )

    assert response.data == {"success_count": len(expected_ids), "fail_count": 0}
    for device_id in range(2, 8):
        device = group_devices[f"device-{device_id}"]
        action = getattr(device, operation)
        if device_id in expected_ids:
            action.assert_awaited_once_with()
        else:
            action.assert_not_awaited()
