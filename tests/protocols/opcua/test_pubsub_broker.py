"""End-to-end publish/subscribe against Mosquitto or an explicit local test broker."""

import asyncio
from contextlib import suppress
import json
import os
import shutil
import socket
import subprocess
import time
from uuid import uuid4

import aiomqtt
import pytest

from src.proto.opcua.server import OpcUaServer
from tests.protocols.opcua.test_pubsub import DEFINITION, NODE, config, free_port, wait_for


@pytest.fixture
def broker_url(tmp_path):
    if url := os.environ.get("EMS_TEST_MQTT_BROKER_URL"):
        yield url
        return
    executable = shutil.which("mosquitto")
    if executable is None:
        pytest.skip("Install Mosquitto or set EMS_TEST_MQTT_BROKER_URL to an isolated local broker")
    port = free_port()
    settings = tmp_path / "mosquitto.conf"
    settings.write_text(f"listener {port} 127.0.0.1\nallow_anonymous true\npersistence false\n", encoding="utf-8")
    process = subprocess.Popen(
        [executable, "-c", str(settings)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        deadline = time.monotonic() + 5
        while True:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                if process.poll() is not None or time.monotonic() >= deadline:
                    pytest.fail("Local Mosquitto did not start")
                time.sleep(0.02)
        yield f"mqtt://127.0.0.1:{port}"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.asyncio
async def test_broker_delivers_variable_event_and_retained_metadata(broker_url):
    from urllib.parse import urlsplit

    endpoint = urlsplit(broker_url)
    prefix = f"ems-test/{uuid4().hex}"
    publishing = config(broker_url)
    for writer in publishing["writers"]:
        writer["topic"] = f"{prefix}/{writer['name']}"
        writer["metadata_topic"] = f"{writer['topic']}/meta"
    server = OpcUaServer(
        "127.0.0.1",
        free_port(),
        "urn:test:broker",
        definitions=[DEFINITION],
        features={"pubsub": publishing, "events": {"enabled": True}},
    )
    received = []

    async def collect(client):
        async for message in client.messages:
            received.append((str(message.topic), json.loads(message.payload), message.retain))

    try:
        async with aiomqtt.Client(
            endpoint.hostname, endpoint.port or 1883, protocol=aiomqtt.ProtocolVersion.V311, timeout=5
        ) as subscriber:
            await subscriber.subscribe(f"{prefix}/#")
            task = asyncio.create_task(collect(subscriber))
            try:
                await server.start()
                await wait_for(lambda: any(topic == f"{prefix}/power" for topic, _, _ in received))
                await server.write(NODE, 99.0)
                await wait_for(
                    lambda: any(
                        m["Messages"][0]["Payload"].get("Power", {}).get("Value", {}).get("Body") == 99.0
                        for topic, m, _ in received
                        if topic == f"{prefix}/power"
                    )
                )
                await server.emit_event("Broker alarm", 800)
                await wait_for(lambda: any(topic == f"{prefix}/events" for topic, _, _ in received))
                event = next(m for topic, m, _ in received if topic == f"{prefix}/events")
                assert event["Messages"][0]["Payload"]["Message"]["Body"]["Text"] == "Broker alarm"
                # A late subscriber must receive metadata retained by the broker.
                async with aiomqtt.Client(endpoint.hostname, endpoint.port or 1883, timeout=5) as late:
                    await late.subscribe(f"{prefix}/power/meta")
                    message = await asyncio.wait_for(anext(late.messages), 5)
                    assert message.retain and json.loads(message.payload)["MessageType"] == "ua-metadata"
            finally:
                await server.stop()
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
    finally:
        await server.stop()
