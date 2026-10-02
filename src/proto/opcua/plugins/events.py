"""UA event subscription restoration without access to SDK objects."""

import asyncio
from contextlib import suppress

from src.proto.opcua.core.feature_config import EventsConfig
from src.proto.opcua.plugins.base import PluginContext


class EventsPlugin:
    def __init__(self):
        self._task = None
        self._generation = -1
        self._error = None

    async def initialize(self, context: PluginContext) -> None:
        self._port = context.events_port
        self._sink = context.event_sink
        self._config = EventsConfig.model_validate(context.config.get("events", {}))
        self._role = context.role
        if self._port is None or self._sink is None:
            raise ValueError("事件插件缺少协议接口或事件出口")

    async def _receive(self, event: dict) -> None:
        if (
            event.get("Severity", 0) >= self._config.minimum_severity
            and self._config.message_filter.casefold() in str(event.get("Message", "")).casefold()
        ):
            fields = set(self._config.returned_fields) | {"EventId", "SourceNode", "Time", "Severity", "Message"}
            await self._sink.emit({"kind": "event", **{key: value for key, value in event.items() if key in fields}})

    async def _restore(self) -> None:
        await self._port.subscribe_events(self._config.model_dump(), self._receive)
        self._generation = self._port.generation
        self._error = None

    async def start(self) -> None:
        if not self._config.enabled:
            return
        if self._role == "server":
            await self._port.enable_events(self._config.model_dump())
        else:
            await self._restore()
            self._task = asyncio.create_task(self._watch(), name="opcua-event-subscription")

    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(0.5)
            if self._port.running and self._port.generation != self._generation:
                try:
                    await self._restore()
                except Exception as exc:
                    self._error = str(exc)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._role == "client":
            await self._port.clear_event_subscription()
        else:
            await self._port.disable_events()

    def status(self) -> dict:
        return {"enabled": self._config.enabled, "generation": self._generation, "error": self._error}
