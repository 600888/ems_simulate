"""Common channel-scoped transport and feature lifecycle."""

import asyncio
from dataclasses import replace
from types import MappingProxyType
from typing import Any

from src.proto.opcua.plugins.registry import PluginRegistry


class UaFacade:
    def __init__(self, core: Any, registry: PluginRegistry):
        self._core = core
        self._registry = registry
        self._running = False
        self._lifecycle_lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._running and self._core.running

    @property
    def endpoint_url(self) -> str:
        return self._core.endpoint_url

    @property
    def connection_error(self) -> str | None:
        return getattr(self._core, "connection_error", None)

    async def start(self) -> None:
        async with self._lifecycle_lock:
            if self.running:
                return
            if self._running:
                await self._registry.stop()
            try:
                await self._core.start()
                await self._registry.start()
            except BaseException:
                self._running = False
                try:
                    await self._registry.stop()
                finally:
                    await self._core.stop()
                raise
            self._running = True

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            self._running = False
            try:
                await self._registry.stop()
            finally:
                await self._core.stop()

    async def configure_feature(self, name: str, config: dict) -> None:
        async with self._lifecycle_lock:
            if self._running:
                await self._registry.reconfigure(name, config)
            else:
                self._registry.context = replace(
                    self._registry.context,
                    config=MappingProxyType({**self._registry.context.config, name: config}),
                )

    async def configure_access(self, security: dict, credentials: dict) -> None:
        """Update trust and user records; connection security remains unchanged."""
        async with self._lifecycle_lock:
            self._core.security.update(trusted=list(security.get("trusted", [])), users=list(security.get("users", [])))
            self._core.credentials.clear()
            self._core.credentials.update(credentials)
            self._registry.context = replace(
                self._registry.context,
                config=MappingProxyType({**self._registry.context.config, "security": dict(self._core.security)}),
            )

    def capabilities(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "transport",
                "role": self._registry.context.role,
                "enabled": True,
                "required": True,
                "running": self.running,
                "reason": None,
            }
        ] + self._registry.capabilities()

    def diagnostics(self) -> dict:
        return self._core.diagnostics.snapshot()
