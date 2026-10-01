"""Basic server NodeSet XML export with no asyncua objects in the plugin."""

from typing import Any

from src.proto.opcua.plugins.base import ModelPort, PluginContext


class ModelIoPlugin:
    def __init__(self):
        self._port: ModelPort | None = None
        self._running = False

    async def initialize(self, context: PluginContext) -> None:
        if context.role != "server" or context.model_port is None:
            raise ValueError("模型插件需要服务端模型接口")
        self._port = context.model_port

    async def start(self) -> None:
        self._running = True

    async def export_nodeset(self) -> bytes:
        if not self._running or self._port is None:
            raise ValueError("请先启动服务端再导出 NodeSet XML")
        return await self._port.export_nodeset()

    async def stop(self) -> None:
        self._running = False
        self._port = None

    def status(self) -> dict[str, Any]:
        return {"format": "NodeSet XML", "scalar_types": ["Boolean", "Int32", "Double"]}
