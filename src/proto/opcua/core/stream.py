"""Bounded channel-scoped events with explicit gaps for slow consumers."""

import asyncio
from collections import deque
from datetime import UTC, datetime
from typing import Any


class ValueStream:
    def __init__(self, capacity: int = 2000):
        self._events: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._sequence = 0
        self._condition = asyncio.Condition()

    async def emit(self, event: dict[str, Any]) -> None:
        async with self._condition:
            self._sequence += 1
            self._events.append({**event, "sequence": self._sequence, "timestamp": datetime.now(UTC).isoformat()})
            self._condition.notify_all()

    def page(self, after: int = 0, limit: int = 500) -> dict[str, Any]:
        oldest = self._events[0]["sequence"] if self._events else self._sequence + 1
        events = [dict(item) for item in self._events if item["sequence"] > after][:limit]
        return {"events": events, "latest_sequence": self._sequence, "gap": after > 0 and after < oldest - 1}

    async def wait(self, after: int, timeout: float = 20) -> dict[str, Any]:
        async with self._condition:
            if after >= self._sequence:
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout)
                except TimeoutError:
                    pass
            return self.page(after)
