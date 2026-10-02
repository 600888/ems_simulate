"""Explicit built-in factories, also discoverable by frozen builds."""

from src.proto.opcua.plugins.address_space import AddressSpacePlugin
from src.proto.opcua.plugins.events import EventsPlugin
from src.proto.opcua.plugins.history import HistoryPlugin
from src.proto.opcua.plugins.model_io import ModelIoPlugin
from src.proto.opcua.plugins.pubsub import PubSubPlugin
from src.proto.opcua.plugins.registry import PluginSpec
from src.proto.opcua.plugins.simulation import SimulationPlugin
from src.proto.opcua.plugins.subscriptions import SubscriptionsPlugin


def builtin_specs() -> tuple[PluginSpec, ...]:
    return (
        PluginSpec("address_space", frozenset({"server"}), frozenset(), "required", AddressSpacePlugin),
        PluginSpec("model_io", frozenset({"server"}), frozenset({"address_space"}), "optional", ModelIoPlugin),
        PluginSpec("simulation", frozenset({"server"}), frozenset({"address_space"}), "optional", SimulationPlugin),
        PluginSpec("subscriptions", frozenset({"client"}), frozenset(), "required", SubscriptionsPlugin),
        PluginSpec("history", frozenset({"server"}), frozenset({"address_space"}), "optional", HistoryPlugin),
        PluginSpec("events", frozenset({"server", "client"}), frozenset(), "optional", EventsPlugin),
        PluginSpec("pubsub", frozenset({"server"}), frozenset({"address_space"}), "optional", PubSubPlugin),
    )
