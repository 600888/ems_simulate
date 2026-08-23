from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any
from uuid import uuid4

from .models import (
    AutoReadConfig,
    AutoReadState,
    AutoReadStatus,
    CycleResult,
    DatasetSnapshot,
    utc_now,
)

ProgressCallback = Callable[[int, int, int, int], None]
CycleRunner = Callable[[AutoReadConfig, asyncio.Event, ProgressCallback], Awaitable[CycleResult]]


class AutoReadConflictError(RuntimeError):
    """A different auto-read configuration is already active."""


class AutoReadTaskManager:
    """Own one cooperative, non-overlapping auto-read task for a device."""

    def __init__(self, runner: CycleRunner, *, repeat: bool = True) -> None:
        self._runner = runner
        self._repeat = repeat
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None
        self._status = AutoReadStatus()
        self._dataset_snapshots: dict[str, DatasetSnapshot] = {}
        self.read_lock = asyncio.Lock()

    def status(self) -> dict[str, Any]:
        return self._status.to_dict()

    def is_running(self) -> bool:
        return self._status.state in (AutoReadState.RUNNING, AutoReadState.STOPPING)

    def current_config(self) -> AutoReadConfig | None:
        return self._status.config

    async def start(self, config: AutoReadConfig) -> dict[str, Any]:
        task = self._task
        if task is not None and not task.done():
            if self._status.state == AutoReadState.RUNNING and self._status.config == config:
                return self.status()
            raise AutoReadConflictError("已有不同配置的自动读取任务正在运行")

        task_id = uuid4().hex
        stop_event = asyncio.Event()
        self._stop_event = stop_event
        self._status = AutoReadStatus(
            state=AutoReadState.RUNNING,
            task_id=task_id,
            config=config,
            started_at=utc_now(),
        )
        self._task = asyncio.create_task(
            self._run(task_id, config, stop_event),
            name=f"auto-read-{task_id[:8]}",
        )
        return self.status()

    async def stop(self, timeout: float = 1.0) -> dict[str, Any]:
        task = self._task
        if task is None or task.done():
            self._set_idle()
            return self.status()

        self._status.state = AutoReadState.STOPPING
        if self._stop_event is not None:
            self._stop_event.set()

        # Do not force-cancel a task that may be awaiting asyncio.to_thread().
        # The native call keeps running after cancellation, which could otherwise
        # make us report idle and allow a second task to use the same connection.
        with suppress(TimeoutError):
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        return self.status()

    async def shutdown(self) -> None:
        await self.stop(timeout=6.0)
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    def update_dataset_snapshot(
        self,
        dataset_ref: str,
        values: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        key = normalize_dataset_ref(dataset_ref)
        previous = self._dataset_snapshots.get(key, DatasetSnapshot())
        self._dataset_snapshots[key] = DatasetSnapshot(
            values=dict(values) if values is not None else previous.values,
            updated_at=utc_now() if values is not None else previous.updated_at,
            last_error=error,
        )

    def get_dataset_snapshot(self, dataset_ref: str) -> dict[str, Any]:
        snapshot = self._dataset_snapshots.get(normalize_dataset_ref(dataset_ref), DatasetSnapshot())
        return snapshot.to_dict()

    async def _run(self, task_id: str, config: AutoReadConfig, stop_event: asyncio.Event) -> None:
        try:
            while not stop_event.is_set():
                self._update_progress(task_id, 0, 0, 0, 0)
                result = await self._runner(
                    config,
                    stop_event,
                    lambda current, total, success, fail: self._update_progress(task_id, current, total, success, fail),
                )
                if self._status.task_id != task_id:
                    return
                self._status.last_cycle_at = utc_now()
                self._status.cycle_count += 1
                self._status.current = result.total
                self._status.total = result.total
                self._status.success = result.success
                self._status.fail = result.fail
                self._status.last_error = None
                if not self._repeat:
                    break
                if stop_event.is_set():
                    break
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=config.cycle_interval_ms / 1000.0)
                except TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if self._status.task_id == task_id:
                self._status.state = AutoReadState.FAILED
                self._status.last_error = str(exc)
        finally:
            if self._status.task_id == task_id and self._status.state != AutoReadState.FAILED:
                self._set_idle()

    def _update_progress(self, task_id: str, current: int, total: int, success: int, fail: int) -> None:
        if self._status.task_id != task_id:
            return
        self._status.current = current
        self._status.total = total
        self._status.success = success
        self._status.fail = fail

    def _set_idle(self) -> None:
        self._status.state = AutoReadState.IDLE
        self._status.current = 0
        self._status.total = 0


def normalize_dataset_ref(value: str) -> str:
    ref = str(value or "").strip()
    slash_index = ref.rfind("/")
    if slash_index < 0 or "$" in ref[slash_index:]:
        return ref
    separator_index = ref.find(".", slash_index)
    if separator_index < 0:
        return ref
    return f"{ref[:separator_index]}${ref[separator_index + 1 :]}"
