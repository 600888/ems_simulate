"""Persistent server history configured through the core history port."""

from src.proto.opcua.core.feature_config import HistoryConfig
from src.proto.opcua.plugins.base import PluginContext


class HistoryPlugin:
    async def initialize(self, context: PluginContext) -> None:
        self._port = context.history_port
        if self._port is None:
            raise ValueError("历史插件缺少历史接口")
        self._config = HistoryConfig.model_validate(context.config.get("history", {}))
        self._running = False
        self._path = context.config.get("history_path")

    async def start(self) -> None:
        if self._config.enabled:
            if not self._path:
                raise ValueError("历史存储目录未配置")
            await self._port.enable_history(self._config.model_dump(), self._path)
        self._running = True

    async def stop(self) -> None:
        if self._config.enabled and self._port is not None:
            await self._port.disable_history()
        self._running = False

    def status(self) -> dict:
        return {
            "enabled": self._config.enabled,
            "nodes": self._config.nodes,
            "retention_days": self._config.retention_days,
        }
