"""OPC UA client facade with its own channel-scoped registry."""

from types import MappingProxyType
from typing import Any

from src.proto.opcua.core.transport import UaClientCore
from src.proto.opcua.facade import UaFacade
from src.proto.opcua.plugins.base import PluginContext
from src.proto.opcua.plugins.builtin import builtin_specs
from src.proto.opcua.plugins.registry import PluginRegistry


class OpcUaClient(UaFacade):
    def __init__(self, endpoint_url: str, timeout_ms: int = 3000, *, channel_id: int = 0):
        core = UaClientCore(endpoint_url, timeout_ms)
        context = PluginContext(
            channel_id=channel_id, role="client", ua_port=core, config=MappingProxyType({"endpoint_url": endpoint_url})
        )
        super().__init__(core, PluginRegistry(context, builtin_specs()))

    async def browse(self, node_id: str = "i=85", limit: int = 100) -> list[dict[str, Any]]:
        return await self._core.browse(node_id, limit)

    async def browse_page(self, node_id: str = "i=85", limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return await self._core.browse_page(node_id, limit, offset)

    async def read(self, node_id: str) -> dict[str, Any]:
        return await self._core.read(node_id)

    async def read_point(self, namespace_uri: str, node_id: str) -> dict[str, Any]:
        resolved = await self._core.resolve_node_id(namespace_uri, node_id)
        return await self._core.read(resolved)

    async def write(self, node_id: str, value: bool | int | float) -> dict[str, Any]:
        return await self._core.write(node_id, value)
