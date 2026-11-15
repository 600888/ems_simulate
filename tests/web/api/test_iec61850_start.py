import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.enums.modbus_def import ProtocolType
from src.web.api.device.router import start_device
from src.web.api.device_group.router import batch_device_operation
from src.web.api.exceptions import OperationError
from src.web.api.schemas import BatchDeviceOperationRequest, DeviceStartRequest


def make_device(protocol=ProtocolType.Iec61850Client, **overrides):
    values = dict(
        device_id=7,
        name="ied",
        protocol_type=protocol,
        iec61850_model_loaded=False,
        icd_path=None,
        check_iec61850_model_cache=Mock(return_value={"cache_exists": False}),
        iec61850_load_model_from_cache=Mock(return_value=True),
        load_iec61850_model=Mock(return_value=True),
        start=AsyncMock(return_value=True),
    )
    return SimpleNamespace(**(values | overrides))


def request_for(*devices):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(device_controller=SimpleNamespace(device_map={d.name: d for d in devices}))
        )
    )


async def start(device):
    return await start_device(DeviceStartRequest(device_name=device.name), request_for(device))


@pytest.mark.asyncio
async def test_start_restores_remote_cache_before_connecting():
    events = []
    device = make_device(
        check_iec61850_model_cache=Mock(return_value={"cache_exists": True}),
        iec61850_load_model_from_cache=Mock(side_effect=lambda: events.append("load") or True),
        start=AsyncMock(side_effect=lambda: events.append("start") or True),
    )
    with patch("src.web.api.device.lifecycle.ChannelService.get_icd_path") as get_path:
        response = await start(device)

    assert response.data is True
    assert events == ["load", "start"]
    get_path.assert_not_called()
    device.load_iec61850_model.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", [ProtocolType.Iec61850Client, ProtocolType.Iec61850Server])
async def test_start_loads_saved_icd_before_starting(protocol, tmp_path):
    icd = tmp_path / "saved.icd"
    icd.write_text("<SCL/>", encoding="utf-8")
    events = []
    device = make_device(
        protocol,
        load_iec61850_model=Mock(side_effect=lambda path: events.append(("load", path)) or True),
        start=AsyncMock(side_effect=lambda: events.append("start") or True),
    )
    with patch("src.web.api.device.lifecycle.ChannelService.get_icd_path", return_value=str(icd)):
        await start(device)

    assert events == [("load", str(icd)), "start"]
    device.iec61850_load_model_from_cache.assert_not_called()


@pytest.mark.asyncio
async def test_start_reuses_loaded_model_without_loading_it_again():
    device = make_device(iec61850_model_loaded=True)
    with patch("src.web.api.device.lifecycle.ChannelService.get_icd_path") as get_path:
        await start(device)

    get_path.assert_not_called()
    device.check_iec61850_model_cache.assert_not_called()
    device.iec61850_load_model_from_cache.assert_not_called()
    device.load_iec61850_model.assert_not_called()
    device.start.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_failed_cache_load_prevents_start_and_reports_the_reason():
    device = make_device(
        check_iec61850_model_cache=Mock(return_value={"cache_exists": True}),
        iec61850_load_model_from_cache=Mock(return_value=False),
    )
    with pytest.raises(OperationError, match="缓存不存在或无法读取"):
        await start(device)
    device.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_server_model_reports_import_requirement():
    device = make_device(ProtocolType.Iec61850Server)
    with (
        patch("src.web.api.device.lifecycle.ChannelService.get_icd_path", return_value=None),
        pytest.raises(OperationError, match="请先导入模型"),
    ):
        await start(device)
    device.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_client_without_saved_model_can_connect_for_online_discovery():
    device = make_device()
    with patch("src.web.api.device.lifecycle.ChannelService.get_icd_path", return_value=None):
        await start(device)
    device.start.assert_awaited_once_with()
    device.iec61850_load_model_from_cache.assert_not_called()


@pytest.mark.asyncio
async def test_missing_icd_file_prevents_start(tmp_path):
    device = make_device(ProtocolType.Iec61850Server)
    with (
        patch("src.web.api.device.lifecycle.ChannelService.get_icd_path", return_value=str(tmp_path / "missing.icd")),
        pytest.raises(OperationError, match="ICD 文件不存在"),
    ):
        await start(device)
    device.load_iec61850_model.assert_not_called()
    device.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_icd_load_prevents_start(tmp_path):
    icd = tmp_path / "broken.icd"
    icd.write_text("invalid", encoding="utf-8")
    device = make_device(ProtocolType.Iec61850Server, load_iec61850_model=Mock(return_value=False))
    with (
        patch("src.web.api.device.lifecycle.ChannelService.get_icd_path", return_value=str(icd)),
        pytest.raises(OperationError, match="模型加载失败"),
    ):
        await start(device)
    device.start.assert_not_awaited()


@pytest.mark.asyncio
async def test_group_start_restores_cache_and_continues_after_one_load_fails():
    broken = make_device(
        name="broken",
        check_iec61850_model_cache=Mock(return_value={"cache_exists": True}),
        iec61850_load_model_from_cache=Mock(return_value=False),
    )
    events = []
    cached = make_device(
        check_iec61850_model_cache=Mock(return_value={"cache_exists": True}),
        iec61850_load_model_from_cache=Mock(side_effect=lambda: events.append("load") or True),
        start=AsyncMock(side_effect=lambda: events.append("start") or True),
    )
    with patch(
        "src.web.api.device_group.router.DeviceGroupService.get_devices_by_group",
        return_value=[{"name": broken.name}, {"name": cached.name}],
    ):
        response = await batch_device_operation(
            BatchDeviceOperationRequest(group_id=1, operation="start"), request_for(broken, cached)
        )
    assert response.data == {"success_count": 1, "fail_count": 1}
    assert events == ["load", "start"]
    broken.start.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["start", "stop"])
@pytest.mark.parametrize("group_id", [0, 1])
async def test_group_operations_run_concurrently_and_isolate_failures(operation, group_id):
    ready = asyncio.Event()
    entered = []
    prepared = set()

    async def prepare(device):
        await asyncio.sleep(0)
        prepared.add(device.name)

    async def operate(index):
        if operation == "start":
            assert f"ied-{index}" in prepared
        entered.append(index)
        if len(entered) == 5:
            ready.set()
        # Every device must reach the operation before any of them finishes.
        await ready.wait()
        if index == 0:
            raise RuntimeError("connection failed")
        return index != 1

    devices = []
    for index in range(5):

        async def action(index=index):
            return await operate(index)

        devices.append(make_device(name=f"ied-{index}", **{operation: AsyncMock(side_effect=action)}))

    getter = "get_ungrouped_devices" if group_id == 0 else "get_devices_by_group"
    with (
        patch(
            f"src.web.api.device_group.router.DeviceGroupService.{getter}",
            return_value=[{"name": d.name} for d in devices] + [{"name": "missing"}],
        ),
        patch("src.web.api.device_group.router.prepare_device_start", side_effect=prepare) as prepare_start,
    ):
        response = await asyncio.wait_for(
            batch_device_operation(
                BatchDeviceOperationRequest(group_id=group_id, operation=operation), request_for(*devices)
            ),
            timeout=2,
        )

    assert sorted(entered) == list(range(5))
    assert response.data == {"success_count": 3, "fail_count": 3}
    assert prepare_start.await_count == (5 if operation == "start" else 0)
    for device in devices:
        getattr(device, operation).assert_awaited_once_with()
