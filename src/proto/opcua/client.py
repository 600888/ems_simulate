"""OPC UA client facade with its own channel-scoped registry."""

from types import MappingProxyType
from typing import Any, cast

from src.proto.opcua.core.stream import ValueStream
from src.proto.opcua.core.transport import UaClientCore
from src.proto.opcua.facade import UaFacade
from src.proto.opcua.plugins.base import PluginContext
from src.proto.opcua.plugins.builtin import builtin_specs
from src.proto.opcua.plugins.registry import PluginRegistry
from src.proto.opcua.plugins.subscriptions import SubscriptionsPlugin


class OpcUaClient(UaFacade):
    def __init__(
        self,
        endpoint_url: str,
        timeout_ms: int = 3000,
        *,
        channel_id: int = 0,
        features: dict | None = None,
        credentials: dict | None = None,
        rejected=None,
        runtime: dict | None = None,
    ):
        core = UaClientCore(
            endpoint_url,
            timeout_ms,
            security=(features or {}).get("security"),
            credentials=credentials,
            rejected=rejected,
            runtime=runtime,
        )
        self.stream = ValueStream()
        context = PluginContext(
            channel_id=channel_id,
            role="client",
            ua_port=core,
            subscription_port=core,
            event_sink=self.stream,
            events_port=core,
            config=MappingProxyType({"endpoint_url": endpoint_url, **(features or {})}),
        )
        super().__init__(core, PluginRegistry(context, builtin_specs()))

    async def browse(self, node_id: str = "i=85", limit: int = 100) -> list[dict[str, Any]]:
        return await self._core.browse(node_id, limit)

    async def browse_page(self, node_id: str = "i=85", limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return await self._core.browse_page(node_id, limit, offset)

    async def read(self, node_id: str) -> dict[str, Any]:
        return await self._core.read(node_id)

    async def node_capabilities(self, node_id: str) -> dict:
        return await self._core.node_capabilities(node_id)

    async def read_point(self, namespace_uri: str, node_id: str) -> dict[str, Any]:
        resolved = await self._core.resolve_node_id(namespace_uri, node_id)
        return await self._core.read(resolved)

    async def write(self, node_id: str, value: Any) -> dict[str, Any]:
        return await self._core.write(node_id, value)

    async def read_history(
        self,
        node_id: str,
        start: Any,
        end: Any,
        limit: int,
        continuation: str | None = None,
        release: bool = False,
        **options,
    ) -> dict:
        return await self._core.read_history(node_id, start, end, limit, continuation, release, **options)

    async def configure_subscriptions(self, config: dict) -> None:
        async with self._lifecycle_lock:
            plugin = cast(SubscriptionsPlugin, self._registry.feature("subscriptions"))
            await plugin.reconfigure(config)
