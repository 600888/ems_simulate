"""OPC UA server facade composing transport, address space, and model I/O."""

from types import MappingProxyType
from typing import Any, cast

from src.proto.opcua.core.transport import UaServerCore
from src.proto.opcua.facade import UaFacade
from src.proto.opcua.plugins.address_space import AddressSpacePlugin
from src.proto.opcua.plugins.base import PluginContext
from src.proto.opcua.plugins.builtin import builtin_specs
from src.proto.opcua.plugins.model_io import ModelIoPlugin
from src.proto.opcua.plugins.registry import PluginRegistry


class OpcUaServer(UaFacade):
    def __init__(
        self,
        bind_host: str,
        port: int,
        namespace_uri: str,
        *,
        endpoint_path: str = "/ems/",
        definitions: list[dict[str, Any]] | None = None,
        channel_id: int = 0,
        enabled_plugins: set[str] | None = None,
    ):
        core = UaServerCore(bind_host, port, namespace_uri, endpoint_path=endpoint_path)
        definitions_snapshot = tuple(MappingProxyType(dict(item)) for item in (definitions or []))
        context = PluginContext(
            channel_id=channel_id,
            role="server",
            address_space_port=core,
            model_port=core,
            config=MappingProxyType({"namespace_uri": namespace_uri, "definitions": definitions_snapshot}),
        )
        registry = PluginRegistry(context, builtin_specs(), enabled_plugins)
        super().__init__(core, registry)

    @property
    def node_count(self) -> int:
        return self._core.node_count

    async def export_nodeset(self) -> bytes:
        plugin = cast(ModelIoPlugin, self._registry.feature("model_io"))
        return await plugin.export_nodeset()

    async def read(self, node_id: str) -> dict[str, Any]:
        return await self._core.read(node_id)

    async def reset_values(self) -> int:
        return await cast(AddressSpacePlugin, self._registry.feature("address_space")).reset_values()
