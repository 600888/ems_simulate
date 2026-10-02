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


class SimulationPort(Protocol):
    async def write_simulated(self, node_id: str, value: Any) -> dict: ...

    async def guard_simulation(self, node_id: str, policy: str, pause: Any) -> None: ...

    async def clear_simulation_guards(self) -> None: ...


class SubscriptionPort(Protocol):
    @property
    def running(self) -> bool: ...

    async def create_subscription(self, config: dict, callback: Any) -> dict: ...

    async def clear_subscriptions(self) -> None: ...

    async def reconnect(self) -> None: ...


class HistoryPort(Protocol):
    async def enable_history(self, config: dict, path: str) -> None: ...

    async def disable_history(self) -> None: ...


class EventsPort(Protocol):
    @property
    def generation(self) -> int: ...

    @property
    def running(self) -> bool: ...

    async def subscribe_events(self, config: dict, callback: Any) -> None: ...

    async def clear_event_subscription(self) -> None: ...

    async def enable_events(self, config: dict) -> None: ...

    async def disable_events(self) -> None: ...


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
    simulation_port: SimulationPort | None = None
    subscription_port: SubscriptionPort | None = None
    history_port: HistoryPort | None = None
    events_port: EventsPort | None = None


class FeaturePlugin(Protocol):
    async def initialize(self, context: PluginContext) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    def status(self) -> dict[str, Any]: ...
