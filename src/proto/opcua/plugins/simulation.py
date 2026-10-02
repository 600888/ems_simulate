"""Monotonic-clock simulation through a channel's value port."""

import asyncio
from contextlib import suppress
import math
import random
import time
from typing import Any

from src.proto.opcua.core.feature_config import Rule, SimulationConfig
from src.proto.opcua.core.values import INTEGER_RANGES, validate_value
from src.proto.opcua.plugins.base import PluginContext


def rule_value(rule: Rule, elapsed: float, data_type: str, rng: random.Random) -> Any:
    if rule.kind == "fixed":
        return validate_value(data_type, rule.value)
    if rule.kind == "sine":
        phase = 2 * math.pi * ((elapsed + rule.offset_s) % rule.period_s) / rule.period_s
        value = rule.minimum + (rule.maximum - rule.minimum) * (1 + math.sin(phase)) / 2
    elif rule.kind == "random":
        value = rng.uniform(rule.minimum, rule.maximum)
    else:
        steps = math.floor(max(0, elapsed + rule.offset_s) / (rule.interval_ms / 1000))
        span = rule.maximum - rule.minimum
        value = rule.minimum if span == 0 else rule.minimum + (steps * rule.step) % (span + abs(rule.step))
        value = min(rule.maximum, value)
    return validate_value(data_type, round(value) if data_type in INTEGER_RANGES else value)


class SimulationPlugin:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._states: dict[str, dict] = {}
        self._rules: list[Rule] = []
        self._rng = random.Random()
        self._origins: dict[str, float] = {}
        self._paused = False

    async def initialize(self, context: PluginContext) -> None:
        self._port = context.simulation_port
        self._sink = context.event_sink
        if self._port is None:
            raise ValueError("模拟插件需要服务端值接口")
        self._rules = SimulationConfig.model_validate(context.config.get("simulation", {})).rules
        self._definitions = {item["node_id"]: dict(item) for item in context.config.get("definitions", ())}
        for rule in self._rules:
            definition = self._definitions.get(rule.node_id)
            if definition is None:
                raise ValueError(f"模拟节点不存在: {rule.node_id}")
            if rule.kind != "fixed" and definition["data_type"] not in {*INTEGER_RANGES, "Float", "Double"}:
                raise ValueError("波形模拟仅适用于数值标量")
            rule_value(rule, 0, definition["data_type"], self._rng)
            if rule.kind != "fixed":
                validate_value(
                    definition["data_type"],
                    round(rule.minimum) if definition["data_type"] in INTEGER_RANGES else rule.minimum,
                )
                validate_value(
                    definition["data_type"],
                    round(rule.maximum) if definition["data_type"] in INTEGER_RANGES else rule.maximum,
                )
        self._states = {rule.node_id: {"paused": not rule.enabled, "error": None} for rule in self._rules}

    def inherit_runtime(self, previous) -> None:
        self._paused = previous._paused
        self._origins = dict(previous._origins)
        old_rules = {rule.node_id: rule for rule in previous._rules}
        for rule in self._rules:
            old = previous._states.get(rule.node_id)
            if old and rule.enabled and old_rules[rule.node_id].enabled:
                self._states[rule.node_id] = {"paused": old["paused"] if not old["error"] else False, "error": None}
            if not rule.enabled or self._paused:
                self._states[rule.node_id]["paused"] = True

    async def start(self) -> None:
        for rule in self._rules:
            if rule.enabled:
                await self._port.guard_simulation(rule.node_id, rule.write_policy, self._pause)
        self._task = asyncio.create_task(self._run(), name="opcua-simulation")

    def _pause(self, node_id: str) -> None:
        if node_id in self._states:
            self._states[node_id]["paused"] = True

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        for rule in self._rules:
            self._states[rule.node_id]["paused"] = paused or not rule.enabled

    async def _run(self) -> None:
        origin = time.monotonic()
        for rule in self._rules:
            self._origins.setdefault(rule.node_id, origin)
        due = dict.fromkeys(self._states, origin)
        while True:
            now = time.monotonic()
            for rule in self._rules:
                state = self._states[rule.node_id]
                if state["paused"] or now < due[rule.node_id]:
                    continue
                due[rule.node_id] = now + rule.interval_ms / 1000
                try:
                    value = rule_value(
                        rule, now - self._origins[rule.node_id], self._definitions[rule.node_id]["data_type"], self._rng
                    )
                    snapshot = await self._port.write_simulated(rule.node_id, value)
                    if self._sink:
                        await self._sink.emit({"kind": "value", "source": "simulation", **snapshot})
                except Exception as exc:
                    state.update(paused=True, error=str(exc))
            await asyncio.sleep(0.05)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if getattr(self, "_port", None):
            await self._port.clear_simulation_guards()

    def status(self) -> dict:
        return {"rules": [{"node_id": key, **value} for key, value in self._states.items()]}
