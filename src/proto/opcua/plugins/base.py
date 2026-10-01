"""Narrow contracts for OPC UA feature plugins."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


class UaPort(Protocol):
    async def read(self, node_id: str) -> dict[str, Any]: ...


class NodeRepository(Protocol):
    def list_nodes(self, channel_id: int) -> list[dict[str, Any]]: ...


class AddressSpacePort(Protocol):
    async def install_variables(self, definitions: list[dict[str, Any]]) -> None: ...

    async def reset_variables(self, definitions: list[dict[str, Any]]) -> int: ...


class ModelPort(Protocol):
    async def export_nodeset(self) -> bytes: ...


class EventSink(Protocol):
    async def emit(self, event: Mapping[str, Any]) -> None: ...


@dataclass(frozen=True)
class PluginContext:
    channel_id: int
    role: str
    config: Mapping[str, Any]
    ua_port: UaPort | None = None
    repository: NodeRepository | None = None
    event_sink: EventSink | None = None
    address_space_port: AddressSpacePort | None = None
    model_port: ModelPort | None = None


class FeaturePlugin(Protocol):
    async def initialize(self, context: PluginContext) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def status(self) -> dict[str, Any]: ...
