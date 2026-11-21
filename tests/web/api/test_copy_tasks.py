"""Background copy ownership, live progress, failure accounting and responsive polling."""

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.data.dao.point_dao import PointDao
from src.data.service.device_service import DeviceService
from src.data.service.iec61850_copy_service import Iec61850CopyResult
from src.web.api.channel import device_manage
from src.web.api.exceptions import ConflictError, NotFoundError
from src.web.api.schemas.channel import CopyDeviceRequest, CopySingleDeviceRequest
from src.web.copy_tasks import DeviceCopyTaskManager


def request_for(manager):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                device_copy_tasks=manager, device_controller=SimpleNamespace(device_list=[], device_map={})
            )
        )
    )


@pytest.mark.asyncio
async def test_submission_returns_before_copy_and_progress_survives_request_cancellation(monkeypatch):
    started, finish = asyncio.Event(), asyncio.Event()

    async def slow_copy(req, request, progress):
        progress(1, status="running", stage="points", progress=50, points_completed=25, points_total=50)
        started.set()
        await finish.wait()
        progress(1, status="completed", stage="completed", progress=100)

    monkeypatch.setattr(device_manage.ChannelService, "get_channel_by_id", lambda channel_id: {"name": "Source"})
    monkeypatch.setattr(device_manage, "_copy_device", slow_copy)
    manager = DeviceCopyTaskManager()
    request = request_for(manager)
    submitted = await asyncio.wait_for(
        device_manage.start_copy_task(CopyDeviceRequest(channel_id=1, count=1, suffix="_COPY"), request), 2
    )
    job = manager.get(submitted.data["id"])
    assert submitted.data["items"][0]["name"] == "Source_COPY1"
    assert submitted.data["completed"] == 0
    await started.wait()
    progress = await device_manage.get_copy_task(job.id, request)
    assert progress.data["progress"] == 50
    assert progress.data["items"][0]["points_completed"] == 25

    # A browser disconnect or cancelled polling request never owns the worker.
    async def disconnected_request():
        await device_manage.get_copy_task(job.id, request)
        await asyncio.Event().wait()

    observer = asyncio.create_task(disconnected_request())
    await asyncio.sleep(0)
    observer.cancel()
    await asyncio.gather(observer, return_exceptions=True)
    assert not job.task.done()
    assert (await device_manage.get_active_copy_task(request)).data["id"] == job.id
    finish.set()
    await manager.close()
    assert job.snapshot()["copied_count"] == 1
    assert job.snapshot()["progress"] == 100
    assert (await device_manage.get_active_copy_task(request)).data is None


@pytest.mark.asyncio
async def test_task_failure_preserves_finished_results_and_marks_unprocessed_rows():
    async def failing_copy(progress):
        progress(1, status="completed", progress=100)
        progress(2, status="running", stage="configuration", progress=15)
        raise RuntimeError("Model could not be copied")

    manager = DeviceCopyTaskManager()
    job = manager.start(1, "Source", ["One", "Two", "Three"], failing_copy)
    await job.task
    snapshot = job.snapshot()
    assert snapshot["status"] == "failed"
    assert [item["status"] for item in snapshot["items"]] == ["completed", "failed", "skipped"]
    assert (snapshot["copied_count"], snapshot["failed_count"], snapshot["skipped_count"]) == (1, 1, 1)
    assert snapshot["completed"] == 3
    assert "Model" in snapshot["error"]
    snapshot["items"][0]["progress"] = 0
    assert job.items[0]["progress"] == 100


@pytest.mark.asyncio
async def test_serializes_copy_jobs_and_graceful_shutdown_waits():
    finish = asyncio.Event()

    async def copy(progress):
        await finish.wait()
        progress(1, status="completed", progress=100)

    manager = DeviceCopyTaskManager()
    job = manager.start(1, "Source", ["Target"], copy)
    with pytest.raises(ConflictError):
        manager.start(1, "Source", ["Target"], copy)
    closing = asyncio.create_task(manager.close())
    await asyncio.sleep(0)
    assert not closing.done()
    assert not job.task.cancelled()
    finish.set()
    await closing
    assert job.status == "completed"
    with pytest.raises(ConflictError):
        manager.start(1, "Source", ["Other"], copy)
    with pytest.raises(NotFoundError):
        manager.get("missing")


@pytest.mark.asyncio
async def test_actual_copy_yields_during_slow_point_writes_and_reports_warnings(monkeypatch):
    source = {
        "id": 1,
        "device_id": 10,
        "code": "SOURCE",
        "name": "Source",
        "protocol_type": 1,
        "conn_type": 1,
        "ip": "127.0.0.1",
        "port": 502,
    }
    started, release = threading.Event(), threading.Event()
    calls = 0

    def write_point(channel_id, frame_type, data):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            if not release.wait(5):
                raise RuntimeError("test did not release slow writer")
        if calls == 2:
            raise ValueError("Invalid point")
        return {"id": 100 + calls}

    monkeypatch.setattr(device_manage.ChannelService, "get_channel_by_id", Mock(return_value=source))
    monkeypatch.setattr(device_manage.ChannelService, "get_channel_by_code", Mock(return_value=None))
    monkeypatch.setattr(device_manage.ChannelService, "create_channel", Mock(return_value=30))
    monkeypatch.setattr(DeviceService, "get_device_by_id", Mock(return_value={"id": 10}))
    monkeypatch.setattr(DeviceService, "create_device", Mock(return_value=20))
    monkeypatch.setattr(DeviceService, "update_device", Mock())
    monkeypatch.setattr(
        PointDao,
        "get_points_by_channel",
        Mock(return_value=[{"id": i, "code": f"P{i}", "name": f"Point {i}", "frame_type": 0} for i in range(1, 31)]),
    )
    monkeypatch.setattr(PointDao, "create_point", write_point)
    monkeypatch.setattr(device_manage.ChannelConfigurationService, "clone_for_channel", Mock())
    monkeypatch.setattr(device_manage.Iec61850CopyService, "clone_for_channel", Mock(return_value=Iec61850CopyResult()))
    monkeypatch.setattr(device_manage.PointMappingService, "clone_for_device", Mock())
    monkeypatch.setattr(device_manage.PointMappingService, "get_all_mappings", Mock(return_value=[]))
    monkeypatch.setattr(
        device_manage,
        "_build_copied_device",
        lambda channel: SimpleNamespace(name="Target", set_device_provider=Mock()),
    )
    manager = DeviceCopyTaskManager()
    request = request_for(manager)
    response = await device_manage.start_single_copy_task(
        CopySingleDeviceRequest(
            channel_id=1, target_name="Target", target_code="TARGET", target_ip="127.0.0.2", target_port=502
        ),
        request,
    )
    job = manager.get(response.data["id"])
    try:
        assert await asyncio.to_thread(started.wait, 3)
        # Polling must complete while the synchronous DAO write is still blocked.
        progress = await asyncio.wait_for(device_manage.get_copy_task(job.id, request), 0.5)
        assert progress.data["items"][0]["stage"] == "points"
        assert progress.data["items"][0]["points_total"] == 30
    finally:
        release.set()
        await manager.close()
    item = job.snapshot()["items"][0]
    assert item["status"] == "warning"
    assert item["points_completed"] == 30
    assert "1 个测点复制失败" in item["message"]
    assert job.snapshot()["copied_count"] == 1
    assert job.snapshot()["warning_count"] == 1


@pytest.mark.asyncio
async def test_skipped_existing_device_has_terminal_progress(monkeypatch):
    source = {"id": 1, "code": "SOURCE", "name": "Source", "protocol_type": 1, "conn_type": 1}
    monkeypatch.setattr(device_manage.ChannelService, "get_channel_by_id", Mock(return_value=source))
    monkeypatch.setattr(device_manage.ChannelService, "get_channel_by_code", Mock(return_value=source))
    monkeypatch.setattr(PointDao, "get_points_by_channel", Mock(return_value=[]))
    manager = DeviceCopyTaskManager()
    response = await device_manage.start_copy_task(CopyDeviceRequest(channel_id=1, count=2), request_for(manager))
    job = manager.get(response.data["id"])
    await manager.close()
    assert job.snapshot()["skipped_count"] == 2
    assert job.snapshot()["progress"] == 100
