"""Application-owned copy tasks; HTTP requests only submit and observe work."""

import asyncio
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass
import time
from uuid import uuid4

from src.web.api.exceptions import ConflictError, NotFoundError


@dataclass
class DeviceCopyTask:
    id: str
    source_channel_id: int
    source_name: str
    items: list[dict]
    status: str = "running"
    error: str | None = None
    finished_at: float | None = None
    task: asyncio.Task | None = None

    def update(self, index: int, **changes):
        self.items[index - 1].update(changes)

    def snapshot(self) -> dict:
        finished = [item for item in self.items if item["status"] not in ("pending", "running")]
        return {
            "id": self.id,
            "source_channel_id": self.source_channel_id,
            "source_name": self.source_name,
            "status": self.status,
            "total": len(self.items),
            "completed": len(finished),
            "progress": int(sum(item["progress"] for item in self.items) / len(self.items)),
            "copied_count": sum(item["status"] in ("completed", "warning") for item in self.items),
            "failed_count": sum(item["status"] == "failed" for item in self.items),
            "skipped_count": sum(item["status"] == "skipped" for item in self.items),
            "warning_count": sum(item["status"] == "warning" for item in self.items),
            "error": self.error,
            "items": deepcopy(self.items),
        }


class DeviceCopyTaskManager:
    def __init__(self):
        self.tasks: dict[str, DeviceCopyTask] = {}
        self.closing = False

    def start(self, channel_id: int, source_name: str, names: list[str], runner: Callable[..., Awaitable]):
        if self.closing:
            raise ConflictError("服务正在关闭，无法开始复制")
        if any(task.status == "running" for task in self.tasks.values()):
            raise ConflictError("已有设备复制任务正在运行，请等待完成后再开始")
        for task_id, task in list(self.tasks.items()):
            if task.finished_at is not None and time.monotonic() - task.finished_at > 3600:
                del self.tasks[task_id]
        finished = sorted(self.tasks.values(), key=lambda task: task.finished_at or 0)
        for task in finished[: max(0, len(self.tasks) - 15)]:
            del self.tasks[task.id]
        job = DeviceCopyTask(
            id=uuid4().hex,
            source_channel_id=channel_id,
            source_name=source_name,
            items=[
                {
                    "index": index,
                    "name": name,
                    "status": "pending",
                    "stage": "pending",
                    "progress": 0,
                    "points_completed": 0,
                    "points_total": 0,
                    "message": "",
                }
                for index, name in enumerate(names, 1)
            ],
        )
        self.tasks[job.id] = job
        job.task = asyncio.create_task(self._run(job, runner), name=f"device-copy-{job.id}")
        return job

    async def _run(self, job: DeviceCopyTask, runner: Callable[..., Awaitable]):
        try:
            await runner(job.update)
            job.status = "completed"
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            for item in job.items:
                if item["status"] == "running":
                    item.update(status="failed", stage="failed", progress=100, message=str(exc))
                elif item["status"] == "pending":
                    item.update(status="skipped", stage="skipped", progress=100, message="任务异常，未执行复制")
        finally:
            job.finished_at = time.monotonic()

    def get(self, task_id: str) -> DeviceCopyTask:
        job = self.tasks.get(task_id)
        if job is None:
            raise NotFoundError("复制任务不存在或已过期")
        return job

    async def close(self):
        # A device copy may already have committed records. Finish its current
        # work before the application releases runtime objects and the database.
        self.closing = True
        await asyncio.gather(*(asyncio.shield(job.task) for job in self.tasks.values() if job.task))
