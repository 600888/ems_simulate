"""Dependency checked, per-channel asynchronous plugin lifecycle."""

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

from src.proto.opcua.plugins.base import FeaturePlugin, PluginContext


@dataclass(frozen=True)
class PluginSpec:
    name: str
    roles: frozenset[str]
    requires: frozenset[str]
    failure_policy: Literal["required", "optional"]
    factory: Callable[[], FeaturePlugin]


class PluginRegistry:
    def __init__(self, context: PluginContext, specs: Iterable[PluginSpec], enabled: set[str] | None = None):
        self.context = context
        role_specs = [spec for spec in specs if context.role in spec.roles]
        if len({spec.name for spec in role_specs}) != len(role_specs):
            raise ValueError("OPC UA 插件名称重复")
        self._all_specs = {spec.name: spec for spec in role_specs}
        self._specs = dict(self._all_specs)
        if enabled is not None:
            unknown = enabled - self._specs.keys()
            if unknown:
                raise ValueError(f"未知或角色不匹配的 OPC UA 插件: {', '.join(sorted(unknown))}")
            self._specs = {name: spec for name, spec in self._specs.items() if name in enabled}
        self._order = self._resolve_order()
        self._instances: dict[str, FeaturePlugin] = {}
        self._started: list[str] = []
        self._states: dict[str, dict[str, str | bool | None]] = {
            name: {"running": False, "reason": None} for name in self._specs
        }

    def _resolve_order(self) -> list[str]:
        order: list[str] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visiting:
                raise ValueError(f"OPC UA 插件存在依赖环: {name}")
            if name in visited:
                return
            visiting.add(name)
            for required in sorted(self._specs[name].requires):
                if required not in self._specs:
                    raise ValueError(f"OPC UA 插件 {name} 缺少依赖 {required}")
                visit(required)
            visiting.remove(name)
            visited.add(name)
            order.append(name)

        for plugin_name in sorted(self._specs):
            visit(plugin_name)
        return order

    async def start(self) -> None:
        for name in self._order:
            if name in self._started:
                continue
            spec = self._specs[name]
            if any(not self._states[required]["running"] for required in spec.requires):
                self._states[name] = {"running": False, "reason": "依赖能力不可用"}
                if spec.failure_policy == "required":
                    await self.stop()
                    raise RuntimeError(f"OPC UA 必需插件 {name} 的依赖不可用")
                continue
            plugin = None
            try:
                plugin = spec.factory()
                self._instances[name] = plugin
                await plugin.initialize(self.context)
                await plugin.start()
            except BaseException as exc:
                try:
                    if plugin is not None:
                        await asyncio.wait_for(plugin.stop(), timeout=5)
                except Exception:
                    pass
                self._states[name] = {"running": False, "reason": str(exc)}
                if not isinstance(exc, Exception):
                    await self.stop()
                    raise
                if spec.failure_policy == "required":
                    await self.stop()
                    raise RuntimeError(f"OPC UA 必需插件 {name} 启动失败: {exc}") from exc
            else:
                self._started.append(name)
                self._states[name] = {"running": True, "reason": None}

    async def stop(self) -> None:
        for name in reversed(self._started):
            try:
                await asyncio.wait_for(self._instances[name].stop(), timeout=5)
            except Exception as exc:
                self._states[name] = {"running": False, "reason": f"停止失败: {exc}"}
            finally:
                if self._states[name]["running"]:
                    self._states[name] = {"running": False, "reason": None}
        self._started.clear()
        self._instances.clear()

    def feature(self, name: str) -> FeaturePlugin:
        if name not in self._started:
            reason = self._states.get(name, {}).get("reason") or "能力尚未启动或已禁用"
            raise ValueError(f"OPC UA 能力 {name} 不可用: {reason}")
        return self._instances[name]

    def capabilities(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "role": self.context.role,
                "enabled": True,
                "required": self._specs[name].failure_policy == "required",
                **self._states[name],
                "details": self._instances[name].status() if name in self._instances else {},
            }
            for name in self._order
        ] + [
            {
                "name": name,
                "role": self.context.role,
                "enabled": False,
                "required": spec.failure_policy == "required",
                "running": False,
                "reason": "已禁用",
            }
            for name, spec in sorted(self._all_specs.items())
            if name not in self._specs
        ]
