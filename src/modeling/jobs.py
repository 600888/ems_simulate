"""Bounded in-process jobs for large IEC 61850 modeling operations."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Event, RLock
from typing import Any
import uuid

ProgressCallback = Callable[[str, int, int, str], None]
CancelCheck = Callable[[], None]
JobHandler = Callable[[ProgressCallback, CancelCheck], dict[str, Any]]


class OperationCancelledError(Exception):
    """Raised cooperatively when a modeling job is cancelled."""


@dataclass(slots=True)
class _Job:
    id: str
    operation: str
    input_size: int
    status: str = "QUEUED"
    phase: str = "queued"
    progress: int = 0
    message: str = "Waiting for a worker"
    result: dict[str, Any] | None = None
    error: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_event: Event = field(default_factory=Event)
    future: Future[Any] | None = None


class ModelingJobManager:
    """Small bounded executor with monotonic progress and cooperative cancellation."""

    def __init__(self, *, max_workers: int = 2, max_pending_jobs: int = 8, max_retained_jobs: int = 128):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="iec61850-modeling")
        self._max_pending_jobs = max_pending_jobs
        self._max_retained_jobs = max_retained_jobs
        self._jobs: dict[str, _Job] = {}
        self._lock = RLock()

    def submit(self, operation: str, handler: JobHandler, *, input_size: int = 0) -> dict[str, Any]:
        job = _Job(id=str(uuid.uuid4()), operation=operation, input_size=input_size)
        with self._lock:
            self._prune_locked()
            active = sum(job.status in {"QUEUED", "RUNNING", "CANCELLING"} for job in self._jobs.values())
            if active >= self._max_pending_jobs:
                raise RuntimeError("The modeling job queue is full; retry after an active job finishes.")
            self._jobs[job.id] = job
            job.future = self._executor.submit(self._run, job, handler)
            return self._snapshot(job)

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return self._snapshot(job) if job else None

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job.status in {"COMPLETED", "FAILED", "CANCELLED"}:
                return self._snapshot(job)
            job.cancel_event.set()
            if job.future and job.future.cancel():
                job.status = "CANCELLED"
                job.phase = "cancelled"
                job.message = "Cancelled before execution"
                job.finished_at = datetime.now(UTC)
            else:
                job.status = "CANCELLING"
                job.message = "Cancellation requested"
            return self._snapshot(job)

    def _run(self, job: _Job, handler: JobHandler) -> None:
        with self._lock:
            if job.cancel_event.is_set():
                self._finish_cancelled(job)
                return
            job.status = "RUNNING"
            job.phase = "starting"
            job.message = "Started"
            job.started_at = datetime.now(UTC)

        def check_cancel() -> None:
            if job.cancel_event.is_set():
                raise OperationCancelledError

        def report(phase: str, current: int, total: int, message: str) -> None:
            check_cancel()
            percent = 0 if total <= 0 else int(current * 100 / total)
            with self._lock:
                job.phase = phase
                job.progress = max(job.progress, min(max(percent, 0), 99))
                job.message = message

        try:
            result = handler(report, check_cancel)
            check_cancel()
        except OperationCancelledError:
            with self._lock:
                self._finish_cancelled(job)
        except Exception as exc:  # jobs must retain a diagnostic instead of escaping the worker
            with self._lock:
                job.status = "FAILED"
                job.phase = "failed"
                job.error = str(exc)
                job.message = str(exc)
                job.finished_at = datetime.now(UTC)
        else:
            with self._lock:
                job.status = "COMPLETED"
                job.phase = "completed"
                job.progress = 100
                job.message = "Completed"
                job.result = result
                job.finished_at = datetime.now(UTC)

    @staticmethod
    def _finish_cancelled(job: _Job) -> None:
        job.status = "CANCELLED"
        job.phase = "cancelled"
        job.message = "Cancelled"
        job.finished_at = datetime.now(UTC)

    def _prune_locked(self) -> None:
        if len(self._jobs) < self._max_retained_jobs:
            return
        finished = sorted(
            (job for job in self._jobs.values() if job.finished_at is not None),
            key=lambda item: item.finished_at or item.created_at,
        )
        while len(self._jobs) >= self._max_retained_jobs and finished:
            self._jobs.pop(finished.pop(0).id, None)

    @staticmethod
    def _snapshot(job: _Job) -> dict[str, Any]:
        return {
            "id": job.id,
            "operation": job.operation,
            "status": job.status,
            "phase": job.phase,
            "progress": job.progress,
            "message": job.message,
            "input_size": job.input_size,
            "result": job.result,
            "error": job.error,
            "created_at": job.created_at.isoformat(),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        }
