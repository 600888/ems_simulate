"""Install the channel's stable scalar variable definitions through a narrow port."""

from typing import Any

from src.proto.opcua.core.model import validate_variable
from src.proto.opcua.plugins.base import AddressSpacePort, PluginContext


class AddressSpacePlugin:
    def __init__(self):
        self._port: AddressSpacePort | None = None
        self._definitions: list[dict[str, Any]] = []
        self._running = False

    async def initialize(self, context: PluginContext) -> None:
        if context.role != "server" or context.address_space_port is None:
            raise ValueError("地址空间插件需要服务端地址空间接口")
        self._port = context.address_space_port
        namespace_uri = context.config["namespace_uri"]
        seen: set[str] = set()
        self._definitions = []
        for definition in context.config.get("definitions", ()):
            normalized = validate_variable(dict(definition))
            if definition.get("namespace_uri", namespace_uri) != namespace_uri:
                raise ValueError("节点定义与服务端命名空间 URI 不一致")
            if normalized["node_id"] in seen:
                raise ValueError(f"重复 NodeId: {normalized['node_id']}")
            seen.add(normalized["node_id"])
            self._definitions.append(normalized)

    async def start(self) -> None:
        if self._port is None:
            raise RuntimeError("地址空间插件尚未初始化")
        await self._port.install_variables(self._definitions)
        self._running = True

    async def stop(self) -> None:
        self._running = False
        self._definitions.clear()
        self._port = None

    async def reset_values(self) -> int:
        if not self._running or self._port is None:
            raise ValueError("地址空间尚未启动")
        return await self._port.reset_variables(self._definitions)

    def status(self) -> dict[str, Any]:
        return {"node_count": len(self._definitions), "schema_version": 1}
