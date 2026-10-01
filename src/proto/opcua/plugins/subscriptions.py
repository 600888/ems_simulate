"""Desired subscriptions survive a new UA session; SDK objects stay in core."""

import asyncio
from contextlib import suppress

from src.proto.opcua.core.feature_config import SubscriptionsConfig
from src.proto.opcua.plugins.base import PluginContext


class SubscriptionsPlugin:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._states: list[dict] = []
        self._error: str | None = None
        self._generation = 0

    async def initialize(self, context: PluginContext) -> None:
        self._port = context.subscription_port
        self._sink = context.event_sink
        if self._port is None or self._sink is None:
            raise ValueError("订阅插件需要客户端订阅接口和事件出口")
        self._config = SubscriptionsConfig.model_validate(context.config.get("subscriptions", {}))

    async def _restore(self) -> None:
        self._generation += 1
        generation = self._generation

        async def changed(snapshot: dict) -> None:
            if generation == self._generation:
                await self._sink.emit({"kind": "value", "source": "subscription", **snapshot})

        await self._port.clear_subscriptions()
        self._states = []
        for config in self._config.subscriptions:
            if not config.enabled:
                self._states.append({"id": config.id, "running": False, "paused": True, "items": []})
                continue
            try:
                self._states.append(await self._port.create_subscription(config.model_dump(), changed))
            except Exception as exc:
                self._states.append({"id": config.id, "running": False, "error": str(exc), "items": []})
        self._error = None
        await self._sink.emit({"kind": "connection", "state": "connected", "generation": generation})

    async def start(self) -> None:
        if self._port.running:
            await self._restore()
        self._task = asyncio.create_task(self._watch(), name="opcua-subscriptions-reconnect")

    async def _watch(self) -> None:
        delay = self._config.retry_min_s
        lost = False
        while True:
            await asyncio.sleep(0.2)
            if self._port.running:
                delay = self._config.retry_min_s
                lost = False
                continue
            if not lost:
                lost = True
                self._generation += 1
                for state in self._states:
                    state["running"] = False
                await self._sink.emit({"kind": "connection", "state": "disconnected"})
            if not self._config.reconnect:
                continue
            await asyncio.sleep(delay)
            try:
                await self._port.reconnect()
                await self._restore()
            except Exception as exc:
                self._error = str(exc)
                delay = min(self._config.retry_max_s, delay * 2)

    async def stop(self) -> None:
        self._generation += 1
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if getattr(self, "_port", None):
            await self._port.clear_subscriptions()
        for state in self._states:
            state["running"] = False

    async def reconfigure(self, config: dict) -> None:
        validated = SubscriptionsConfig.model_validate(config)
        await self.stop()
        self._config = validated
        await self.start()

    def status(self) -> dict:
        return {"subscriptions": self._states, "generation": self._generation, "error": self._error}
