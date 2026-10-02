"""OPC UA server facade composing transport, address space, and model I/O."""

from types import MappingProxyType
from typing import Any, cast

from src.proto.opcua.core.stream import ValueStream
from src.proto.opcua.core.transport import UaServerCore
from src.proto.opcua.facade import UaFacade
from src.proto.opcua.plugins.address_space import AddressSpacePlugin
from src.proto.opcua.plugins.base import PluginContext
from src.proto.opcua.plugins.builtin import builtin_specs
from src.proto.opcua.plugins.model_io import ModelIoPlugin
from src.proto.opcua.plugins.registry import PluginRegistry
from src.proto.opcua.plugins.simulation import SimulationPlugin


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
        features: dict | None = None,
        credentials: dict | None = None,
        rejected=None,
    ):
        core = UaServerCore(
            bind_host,
            port,
            namespace_uri,
            endpoint_path=endpoint_path,
            security=(features or {}).get("security"),
            credentials=credentials,
            rejected=rejected,
        )
        definitions_snapshot = tuple(MappingProxyType(dict(item)) for item in (definitions or []))
        self.stream = ValueStream()
        context = PluginContext(
            channel_id=channel_id,
            role="server",
            address_space_port=core,
            model_port=core,
            simulation_port=core,
            history_port=core,
            events_port=core,
            event_sink=self.stream,
            config=MappingProxyType(
                {"namespace_uri": namespace_uri, "definitions": definitions_snapshot, **(features or {})}
            ),
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

    async def browse_page(self, node_id: str, limit: int = 100, offset: int = 0) -> dict:
        return await self._core.browse_page(node_id, limit, offset)

    async def inspect_node(self, node_id: str) -> dict:
        return await self._core.inspect_node(node_id)

    async def write(self, node_id: str, value: Any) -> dict:
        return await self._core.write(node_id, value)

    async def reset_values(self) -> int:
        return await cast(AddressSpacePlugin, self._registry.feature("address_space")).reset_values()

    async def emit_event(self, message: str, severity: int) -> dict:
        self._registry.feature("events")
        result = await self._core.emit_event(message, severity)
        await self.stream.emit({"kind": "event", **result})
        return result

    def pause_simulation(self, paused: bool) -> None:
        cast(SimulationPlugin, self._registry.feature("simulation")).set_paused(paused)
