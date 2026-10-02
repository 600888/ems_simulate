"""OPC UA server facade composing transport, address space, and model I/O."""

from dataclasses import replace
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

    async def configure_definitions(self, definitions: list[dict], features: dict) -> None:
        async with self._lifecycle_lock:
            old_context = self._registry.context
            context = replace(
                old_context,
                config=MappingProxyType({**old_context.config, **features, "definitions": tuple(definitions)}),
            )
            if not self._running:
                self._registry.context = context
                return
            self._core.validate_variable_changes(definitions)
            validator = SimulationPlugin()
            await validator.initialize(context)
            old_definitions = list(old_context.config.get("definitions", ()))
            removed = {item["node_id"] for item in old_definitions} - {item["node_id"] for item in definitions}
            removed_values = {key: await self._core._node(key).read_data_value() for key in removed}
            address_space = cast(AddressSpacePlugin, self._registry.feature("address_space"))
            old_by_id = {item["node_id"]: item for item in old_definitions}
            access_changed = {
                item["node_id"]
                for item in definitions
                if item["node_id"] in old_by_id and item["writable"] != old_by_id[item["node_id"]]["writable"]
            }
            simulated = {rule["node_id"] for rule in old_context.config.get("simulation", {}).get("rules", [])}
            names = [
                name
                for name in ("simulation", "history", "events")
                if name in self._registry._started
                and (
                    old_context.config.get(name, {}) != context.config.get(name, {})
                    or (name == "simulation" and bool((removed | access_changed) & simulated))
                )
            ]
            try:
                for name in names:
                    await self._registry.feature(name).stop()
                await self._core.sync_variables(definitions)
                self._registry.context = context
                address_space.update_definitions(definitions)
                for name in names:
                    await self._registry.reconfigure(name, dict(context.config.get(name, {})))
            except BaseException:
                for name in names:
                    await self._registry.feature(name).stop()
                await self._core.sync_variables(old_definitions)
                for key, value in removed_values.items():
                    await self._core._node(key).write_value(value)
                self._registry.context = old_context
                address_space.update_definitions(old_definitions)
                for name in names:
                    await self._registry.reconfigure(name, dict(old_context.config.get(name, {})))
                raise
