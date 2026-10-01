import asyncio

import pytest

from src.proto.opcua.plugins.base import PluginContext
from src.proto.opcua.plugins.registry import PluginRegistry, PluginSpec


class DemoPlugin:
    def __init__(self, name, calls, fail=False):
        self.name = name
        self.calls = calls
        self.fail = fail

    async def initialize(self, context):
        self.calls.append((self.name, "initialize", context.channel_id))

    async def start(self):
        self.calls.append((self.name, "start"))
        if self.fail:
            raise RuntimeError("broken")

    async def stop(self):
        self.calls.append((self.name, "stop"))

    def status(self):
        return {}


def spec(name, calls, *, requires=(), fail=False, policy="required", roles=("client",)):
    return PluginSpec(
        name=name,
        roles=frozenset(roles),
        requires=frozenset(requires),
        failure_policy=policy,
        factory=lambda: DemoPlugin(name, calls, fail),
    )


@pytest.mark.asyncio
async def test_dependency_order_and_reverse_cleanup():
    calls = []
    registry = PluginRegistry(
        PluginContext(channel_id=1, role="client", config={}),
        [spec("trend", calls, requires=("subscription",)), spec("subscription", calls)],
    )
    await registry.start()
    assert [entry[:2] for entry in calls if entry[1] == "start"] == [("subscription", "start"), ("trend", "start")]
    assert all(item["running"] for item in registry.capabilities())
    await registry.stop()
    assert [entry[0] for entry in calls if entry[1] == "stop"] == ["trend", "subscription"]


@pytest.mark.asyncio
async def test_optional_failure_is_visible_and_required_failure_rolls_back():
    calls = []
    optional = PluginRegistry(
        PluginContext(channel_id=1, role="client", config={}),
        [
            spec("core_feature", calls),
            spec("optional", calls, requires=("core_feature",), fail=True, policy="optional"),
        ],
    )
    await optional.start()
    states = {item["name"]: item for item in optional.capabilities()}
    assert states["core_feature"]["running"] is True
    assert states["optional"]["reason"] == "broken"
    await optional.stop()

    calls.clear()
    required = PluginRegistry(
        PluginContext(channel_id=2, role="client", config={}),
        [spec("base", calls), spec("broken", calls, requires=("base",), fail=True)],
    )
    with pytest.raises(RuntimeError, match="broken"):
        await required.start()
    assert ("base", "stop") in calls
    assert not any(item["running"] for item in required.capabilities())


def test_dependency_validation_and_disabled_capability():
    context = PluginContext(channel_id=1, role="client", config={})
    with pytest.raises(ValueError, match="缺少依赖"):
        PluginRegistry(context, [spec("a", [], requires=("missing",))])
    with pytest.raises(ValueError, match="依赖环"):
        PluginRegistry(context, [spec("a", [], requires=("b",)), spec("b", [], requires=("a",))])
    registry = PluginRegistry(context, [spec("a", []), spec("server_only", [], roles=("server",))], enabled=set())
    assert registry.capabilities()[0]["reason"] == "已禁用"


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", ["required", "optional"])
async def test_factory_failure_obeys_failure_policy(policy):
    calls = []

    def broken_factory():
        raise RuntimeError("factory broken")

    registry = PluginRegistry(
        PluginContext(channel_id=1, role="client", config={}),
        [
            spec("base", calls),
            PluginSpec("broken", frozenset({"client"}), frozenset({"base"}), policy, broken_factory),
        ],
    )
    try:
        if policy == "required":
            with pytest.raises(RuntimeError, match="factory broken"):
                await registry.start()
            assert ("base", "stop") in calls
        else:
            await registry.start()
            assert registry.capabilities()[0]["running"]
        assert registry.capabilities()[1]["reason"] == "factory broken"
    finally:
        await registry.stop()


@pytest.mark.asyncio
async def test_cancelled_start_stops_started_dependencies():
    calls = []

    class CancelledPlugin(DemoPlugin):
        async def start(self):
            raise asyncio.CancelledError

    registry = PluginRegistry(
        PluginContext(channel_id=1, role="client", config={}),
        [
            spec("base", calls),
            PluginSpec(
                "cancelled",
                frozenset({"client"}),
                frozenset({"base"}),
                "optional",
                lambda: CancelledPlugin("cancelled", calls),
            ),
        ],
    )
    with pytest.raises(asyncio.CancelledError):
        await registry.start()
    assert ("base", "stop") in calls and ("cancelled", "stop") in calls
    assert not any(item["running"] for item in registry.capabilities())
