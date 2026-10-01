"""Explicit built-in factories, also discoverable by frozen builds."""

from src.proto.opcua.plugins.address_space import AddressSpacePlugin
from src.proto.opcua.plugins.model_io import ModelIoPlugin
from src.proto.opcua.plugins.registry import PluginSpec


def builtin_specs() -> tuple[PluginSpec, ...]:
    return (
        PluginSpec("address_space", frozenset({"server"}), frozenset(), "required", AddressSpacePlugin),
        PluginSpec("model_io", frozenset({"server"}), frozenset({"address_space"}), "optional", ModelIoPlugin),
    )
