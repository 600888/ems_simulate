from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from pydantic import ValidationError as PydanticValidationError
import pytest

from src.device.auto_read import AutoReadConflictError, AutoReadMode
from src.web.api.device.router import (
    get_auto_read_status,
    manual_read,
    manual_read_status,
    start_auto_read,
    stop_auto_read,
)
from src.web.api.exceptions import ConflictError
from src.web.api.schemas import AutoReadStartRequest, DeviceInfoRequest, ManualReadRequest


def _request(device):
    controller = SimpleNamespace(device_map={"dev-1": device})
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(device_controller=controller)))


@pytest.mark.asyncio
async def test_start_auto_read_maps_request_to_backend_config_and_returns_status():
    expected = {"state": "running", "task_id": "task-1", "mode": "single"}
    device = SimpleNamespace(
        is_protocol_running=Mock(return_value=True),
        start_auto_read=AsyncMock(return_value=expected),
    )
    req = AutoReadStartRequest(
        device_name="dev-1",
        mode="single",
        cycle_interval_ms=1000,
        request_interval_ms=20,
        slave_id=2,
        point_types=[0, 1],
    )

    response = await start_auto_read(req, _request(device))

    config = device.start_auto_read.await_args.args[0]
    assert config.mode == AutoReadMode.SINGLE
    assert config.request_interval_ms == 20
    assert config.slave_id == 2
    assert response.data == expected


@pytest.mark.asyncio
async def test_start_auto_read_uses_http_409_for_different_active_config():
    device = SimpleNamespace(
        is_protocol_running=Mock(return_value=True),
        start_auto_read=AsyncMock(side_effect=AutoReadConflictError("conflict")),
        get_auto_read_status=Mock(return_value={"state": "running"}),
    )

    with pytest.raises(ConflictError) as exc_info:
        await start_auto_read(AutoReadStartRequest(device_name="dev-1"), _request(device))

    assert exc_info.value.http_status == 409
    assert exc_info.value.data == {"state": "running"}


@pytest.mark.asyncio
async def test_status_and_stop_are_structured_and_stop_is_awaited():
    running = {"state": "running", "task_id": "task-1"}
    idle = {"state": "idle", "task_id": "task-1"}
    device = SimpleNamespace(
        get_auto_read_status=Mock(return_value=running),
        stop_auto_read=AsyncMock(return_value=idle),
    )
    req = DeviceInfoRequest(device_name="dev-1")
    request = _request(device)

    assert (await get_auto_read_status(req, request)).data == running
    assert (await stop_auto_read(req, request)).data == idle
    device.stop_auto_read.assert_awaited_once()


def test_auto_read_interval_validation_rejects_tight_cycles():
    with pytest.raises(PydanticValidationError):
        AutoReadStartRequest(device_name="dev-1", cycle_interval_ms=99)


@pytest.mark.asyncio
async def test_manual_batch_read_submits_one_background_task():
    running = {"state": "running", "task_id": "manual-1", "mode": "batch"}
    device = SimpleNamespace(
        is_protocol_running=Mock(return_value=True),
        start_manual_read=AsyncMock(return_value=running),
        get_manual_read_status=Mock(return_value=running),
    )
    request = _request(device)

    response = await manual_read(
        ManualReadRequest(
            device_name="dev-1",
            interval=20,
            mode="batch",
            point_types=[0, 1],
        ),
        request,
    )

    config = device.start_manual_read.await_args.args[0]
    assert config.mode == AutoReadMode.BATCH
    assert config.request_interval_ms == 20
    assert response.data == running
    assert (await manual_read_status(DeviceInfoRequest(device_name="dev-1"), request)).data == running


@pytest.mark.asyncio
async def test_manual_single_read_submits_one_backend_task_with_point_filters():
    running = {"state": "running", "task_id": "manual-2", "mode": "single"}
    device = SimpleNamespace(
        is_protocol_running=Mock(return_value=True),
        start_manual_read=AsyncMock(return_value=running),
        get_manual_read_status=Mock(return_value=running),
    )

    response = await manual_read(
        ManualReadRequest(
            device_name="dev-1",
            interval=50,
            mode="single",
            slave_id=3,
            category="DataModel",
            item="LD0/LLN0",
            point_types=[0, 2],
            dlt645_prefix=1,
            dlt645_settlement=4,
        ),
        _request(device),
    )

    config = device.start_manual_read.await_args.args[0]
    assert config.mode == AutoReadMode.SINGLE
    assert config.request_interval_ms == 50
    assert config.slave_id == 3
    assert config.category == "DataModel"
    assert config.item == "LD0/LLN0"
    assert config.point_types == (0, 2)
    assert config.dlt645_prefix == 1
    assert config.dlt645_settlement == 4
    assert response.data == running
