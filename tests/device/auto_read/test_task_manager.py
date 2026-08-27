import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.device.auto_read import (
    AutoReadConfig,
    AutoReadConflictError,
    AutoReadMode,
    AutoReadTaskManager,
    CycleResult,
)
from src.device.core.device import Device


@pytest.mark.asyncio
async def test_start_is_idempotent_for_same_config_and_rejects_different_config():
    entered = asyncio.Event()
    release = asyncio.Event()

    async def runner(config, stop_event, progress):
        entered.set()
        await release.wait()
        return CycleResult(total=1, success=1)

    manager = AutoReadTaskManager(runner)
    config = AutoReadConfig(mode=AutoReadMode.BATCH, cycle_interval_ms=100)
    first = await manager.start(config)
    await entered.wait()
    second = await manager.start(config)

    assert second["task_id"] == first["task_id"]
    with pytest.raises(AutoReadConflictError):
        await manager.start(AutoReadConfig(mode=AutoReadMode.SINGLE, cycle_interval_ms=100))

    release.set()
    await manager.stop()


@pytest.mark.asyncio
async def test_stop_interrupts_cycle_wait_without_starting_another_cycle():
    cycle_count = 0

    async def runner(config, stop_event, progress):
        nonlocal cycle_count
        cycle_count += 1
        return CycleResult(total=1, success=1)

    manager = AutoReadTaskManager(runner)
    await manager.start(AutoReadConfig(cycle_interval_ms=60_000))
    while manager.status()["cycle_count"] == 0:
        await asyncio.sleep(0)

    status = await manager.stop()

    assert status["state"] == "idle"
    assert cycle_count == 1


@pytest.mark.asyncio
async def test_cycle_interval_is_measured_from_cycle_start(monkeypatch):
    """协议读取耗时不能再次叠加到界面配置的轮询周期。"""
    captured_timeouts = []
    cycle_count = 0

    class FakeLoop:
        def __init__(self):
            self.times = iter((10.0, 10.025, 10.1))

        def time(self):
            return next(self.times)

    async def fake_wait_for(awaitable, *, timeout):
        awaitable.close()
        captured_timeouts.append(timeout)
        raise TimeoutError

    async def runner(config, stop_event, progress):
        nonlocal cycle_count
        cycle_count += 1
        if cycle_count == 2:
            stop_event.set()
        return CycleResult(total=1, success=1)

    fake_loop = FakeLoop()
    monkeypatch.setattr("src.device.auto_read.task_manager.asyncio.get_running_loop", lambda: fake_loop)
    monkeypatch.setattr("src.device.auto_read.task_manager.asyncio.wait_for", fake_wait_for)

    manager = AutoReadTaskManager(runner)
    task_id = "deadline-test"
    manager._status.task_id = task_id
    await manager._run(task_id, AutoReadConfig(cycle_interval_ms=100), asyncio.Event())

    assert cycle_count == 2
    assert captured_timeouts == pytest.approx([0.075])


@pytest.mark.asyncio
async def test_stop_stays_stopping_until_current_non_cancellable_io_finishes():
    entered = asyncio.Event()
    release = asyncio.Event()

    async def runner(config, stop_event, progress):
        entered.set()
        await release.wait()
        return CycleResult(total=1, success=1)

    manager = AutoReadTaskManager(runner)
    await manager.start(AutoReadConfig(cycle_interval_ms=100))
    await entered.wait()

    status = await manager.stop(timeout=0.001)
    assert status["state"] == "stopping"

    release.set()
    for _ in range(100):
        if manager.status()["state"] == "idle":
            break
        await asyncio.sleep(0)
    assert manager.status()["state"] == "idle"


def test_dataset_snapshot_normalizes_dot_and_dollar_references():
    async def runner(config, stop_event, progress):
        return CycleResult()

    manager = AutoReadTaskManager(runner)
    manager.update_dataset_snapshot("LD0/LLN0.ds1", values={"LD0/X.stVal": True})

    snapshot = manager.get_dataset_snapshot("LD0/LLN0$ds1")
    assert snapshot["values"] == {"LD0/X.stVal": True}
    assert snapshot["stale"] is False


@pytest.mark.asyncio
async def test_non_repeating_manager_runs_exactly_one_cycle():
    cycles = 0

    async def runner(config, stop_event, progress):
        nonlocal cycles
        cycles += 1
        return CycleResult(success=2, total=2)

    manager = AutoReadTaskManager(runner, repeat=False)
    await manager.start(AutoReadConfig(cycle_interval_ms=100))
    for _ in range(100):
        if manager.status()["state"] == "idle":
            break
        await asyncio.sleep(0)

    assert cycles == 1
    assert manager.status()["success"] == 2


@pytest.mark.asyncio
async def test_manager_exposes_live_success_and_fail_counts():
    progress_reported = asyncio.Event()
    release = asyncio.Event()

    async def runner(config, stop_event, progress):
        progress(2, 4, 1, 1)
        progress_reported.set()
        await release.wait()
        return CycleResult(success=3, fail=1, total=4)

    manager = AutoReadTaskManager(runner, repeat=False)
    await manager.start(AutoReadConfig(mode=AutoReadMode.SINGLE, cycle_interval_ms=100))
    await progress_reported.wait()

    running = manager.status()
    assert running["state"] == "running"
    assert running["current"] == 2
    assert running["total"] == 4
    assert running["success"] == 1
    assert running["fail"] == 1

    release.set()
    for _ in range(100):
        if manager.status()["state"] == "idle":
            break
        await asyncio.sleep(0)

    completed = manager.status()
    assert completed["success"] == 3
    assert completed["fail"] == 1


@pytest.mark.asyncio
async def test_single_cycle_reads_selected_points_inside_backend_task():
    points = [
        SimpleNamespace(code="p-1", rtu_addr="1"),
        SimpleNamespace(code="p-2", rtu_addr="2"),
    ]
    point_operator = SimpleNamespace(read_single_point_async=AsyncMock(side_effect=[12.5, None]))
    device = SimpleNamespace(
        is_protocol_running=Mock(return_value=True),
        _select_auto_read_points=Mock(return_value=points),
        auto_read_manager=SimpleNamespace(read_lock=asyncio.Lock()),
        point_operator=point_operator,
    )
    progress_updates = []

    result = await Device._run_auto_read_cycle(
        device,
        AutoReadConfig(mode=AutoReadMode.SINGLE, request_interval_ms=0, slave_id=1),
        asyncio.Event(),
        lambda current, total, success, fail: progress_updates.append((current, total, success, fail)),
    )

    assert result == CycleResult(success=1, fail=1, total=2)
    assert point_operator.read_single_point_async.await_args_list[0].args == ("p-1",)
    assert point_operator.read_single_point_async.await_args_list[0].kwargs == {"slave_id": "1"}
    assert point_operator.read_single_point_async.await_args_list[1].args == ("p-2",)
    assert point_operator.read_single_point_async.await_args_list[1].kwargs == {"slave_id": "2"}
    assert progress_updates == [(1, 2, 1, 0), (2, 2, 1, 1)]
