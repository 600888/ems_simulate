"""Actual TCP subscriptions, reconnection, simulation policies and rich values."""

import asyncio
import random
import socket

from asyncua import ua
import pytest

from src.proto.opcua.client import OpcUaClient
from src.proto.opcua.core.feature_config import Rule
from src.proto.opcua.core.stream import ValueStream
from src.proto.opcua.plugins.simulation import rule_value
from src.proto.opcua.server import OpcUaServer


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def variable(data_type="Double", initial_value=0.0):
    return {
        "node_id": "ns=2;s=power",
        "browse_name": "Power",
        "data_type": data_type,
        "initial_value": initial_value,
        "writable": True,
    }


async def until(predicate, timeout=8):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.05)


def test_waveform_phase_and_integer_boundaries():
    rule = Rule(node_id="ns=2;s=p", minimum=10, maximum=20, period_s=4)
    rng = random.Random(1)
    assert rule_value(rule, 0, "Double", rng) == 15
    assert rule_value(rule, 1, "Double", rng) == 20
    assert rule_value(rule, 3, "Double", rng) == 10
    for time in range(100):
        assert 10 <= rule_value(rule, time / 10, "Int32", rng) <= 20


@pytest.mark.asyncio
async def test_stream_gap_and_channel_isolation():
    first, second = ValueStream(2), ValueStream()
    for value in range(4):
        await first.emit({"kind": "value", "value": value})
    assert first.page(1)["gap"]
    assert [item["sequence"] for item in first.page()["events"]] == [3, 4]
    assert not second.page()["events"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data_type,value,replacement",
    [
        ("String", "initial", "changed"),
        ("UInt16", 0, 65535),
        ("Int64", {"integer": "9223372036854775807"}, {"integer": "-9223372036854775808"}),
        ("ByteString", {"base64": "AAE="}, {"base64": "AgM="}),
        ("DateTime", "2026-10-01T00:00:00+00:00", "2026-10-02T00:00:00+00:00"),
    ],
)
async def test_extended_types_read_write(data_type, value, replacement):
    server = OpcUaServer("127.0.0.1", free_port(), "urn:test:types", definitions=[variable(data_type, value)])
    client = OpcUaClient(server.endpoint_url)
    try:
        await server.start()
        await client.start()
        assert (await client.read("ns=2;s=power"))["value"] == value
        assert (await client.write("ns=2;s=power", replacement))["value"] == replacement
    finally:
        await client.stop()
        await server.stop()


@pytest.mark.asyncio
async def test_subscription_revisions_item_errors_and_reconnect():
    server = OpcUaServer("127.0.0.1", free_port(), "urn:test:sub", definitions=[variable()])
    features = {
        "subscriptions": {
            "retry_min_s": 0.1,
            "retry_max_s": 1,
            "subscriptions": [
                {
                    "id": "power",
                    "publishing_interval_ms": 50,
                    "items": [{"node_id": "ns=2;s=power", "sampling_interval_ms": 50}, {"node_id": "ns=2;s=missing"}],
                }
            ],
        }
    }
    client = OpcUaClient(server.endpoint_url, features=features)
    try:
        await server.start()
        await client.start()
        state = next(item for item in client.capabilities() if item["name"] == "subscriptions")["details"]
        subscription = state["subscriptions"][0]
        assert subscription["publishing_interval_ms"] > 0
        assert subscription["items"][0]["status_code"] == "Good"
        assert subscription["items"][1]["status_code"] == "BadNodeIdUnknown"
        await client.write("ns=2;s=power", 9.0)
        await until(lambda: any(item.get("value") == 9.0 for item in client.stream.page()["events"]))
        await server.stop()
        await until(lambda: not client.running)
        await server.start()
        await until(lambda: client.running)
        await until(
            lambda: (
                next(item for item in client.capabilities() if item["name"] == "subscriptions")["details"]["generation"]
                >= 3
            )
        )
        await client.write("ns=2;s=power", 12.0)
        await until(lambda: any(item.get("value") == 12.0 for item in client.stream.page()["events"]))
        await asyncio.sleep(0.2)
        assert len([item for item in client.stream.page()["events"] if item.get("value") == 12.0]) == 1
        await client.configure_subscriptions({"subscriptions": []})
        before = client.stream.page()["latest_sequence"]
        await client.write("ns=2;s=power", 13.0)
        await asyncio.sleep(0.2)
        assert not any(item.get("value") == 13.0 for item in client.stream.page(before)["events"])
    finally:
        await client.stop()
        await server.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", ["pause", "overwrite", "reject"])
async def test_simulation_external_write_policy(policy):
    server = OpcUaServer(
        "127.0.0.1",
        free_port(),
        "urn:test:sim",
        definitions=[variable()],
        features={
            "simulation": {
                "rules": [
                    {
                        "node_id": "ns=2;s=power",
                        "kind": "fixed",
                        "value": 3.0,
                        "interval_ms": 50,
                        "write_policy": policy,
                    }
                ]
            }
        },
    )
    client = OpcUaClient(server.endpoint_url)
    try:
        await server.start()
        await client.start()
        await until(lambda: bool(server.stream.page()["events"]))
        if policy == "reject":
            with pytest.raises(ua.UaStatusCodeError):
                await client.write("ns=2;s=power", 9.0)
        else:
            await client.write("ns=2;s=power", 9.0)
        await asyncio.sleep(0.15)
        expected = 9.0 if policy == "pause" else 3.0
        assert (await client.read("ns=2;s=power"))["value"] == expected
    finally:
        await client.stop()
        await server.stop()
