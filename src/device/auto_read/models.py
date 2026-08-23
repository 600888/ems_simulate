from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class AutoReadMode(StrEnum):
    BATCH = "batch"
    SINGLE = "single"
    DATASET = "dataset"


class AutoReadState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AutoReadConfig:
    mode: AutoReadMode = AutoReadMode.BATCH
    cycle_interval_ms: int = 1000
    request_interval_ms: int = 0
    slave_id: int | None = None
    channel_id: int | None = None
    category: str = ""
    item: str = ""
    point_types: tuple[int, ...] = ()
    dlt645_prefix: int | None = None
    dlt645_settlement: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["mode"] = self.mode.value
        data["point_types"] = list(self.point_types)
        return data


@dataclass(slots=True)
class CycleResult:
    success: int = 0
    fail: int = 0
    total: int = 0


@dataclass(slots=True)
class AutoReadStatus:
    state: AutoReadState = AutoReadState.IDLE
    task_id: str | None = None
    config: AutoReadConfig | None = None
    started_at: datetime | None = None
    last_cycle_at: datetime | None = None
    cycle_count: int = 0
    current: int = 0
    total: int = 0
    success: int = 0
    fail: int = 0
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "task_id": self.task_id,
            "mode": self.config.mode.value if self.config else None,
            "config": self.config.to_dict() if self.config else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_cycle_at": self.last_cycle_at.isoformat() if self.last_cycle_at else None,
            "cycle_count": self.cycle_count,
            "current": self.current,
            "total": self.total,
            "success": self.success,
            "fail": self.fail,
            "last_error": self.last_error,
        }


@dataclass(slots=True)
class DatasetSnapshot:
    values: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "values": dict(self.values),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_error": self.last_error,
            "stale": self.updated_at is None or self.last_error is not None,
        }


def utc_now() -> datetime:
    return datetime.now(UTC)
