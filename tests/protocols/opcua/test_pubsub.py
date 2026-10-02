"""Real MQTT packets and UA traffic exercise publishing, reconnect and node capabilities."""

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
import json
import socket
import ssl
import struct
from types import SimpleNamespace

import aiomqtt
from asyncua import ua
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pydantic import ValidationError
import pytest

from src.proto.opcua.client import OpcUaClient
from src.proto.opcua.core.feature_config import PubSubConfig
from src.proto.opcua.core.mqtt import MqttPublisher
from src.proto.opcua.core.transport import UaClientCore
from src.proto.opcua.server import OpcUaServer

NODE = "ns=2;s=power"
DEFINITION = {"node_id": NODE, "browse_name": "Power", "data_type": "Double", "initial_value": 12.5, "writable": True}


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def packet(reader):
    header = (await reader.readexactly(1))[0]
    length, factor = 0, 1
    while True:
        byte = (await reader.readexactly(1))[0]
        length += (byte & 127) * factor
        if not byte & 128:
            return header, await reader.readexactly(length)
        factor *= 128


class Broker:
    """Loopback MQTT peer: verifies CONNECT and captures actual PUBLISH frames."""

    def __init__(self):
        self.messages = []
        self.connections = 0
        self.clients = []
        self.tasks = set()

    async def serve(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        self.clients.append(writer)
        try:
            header, body = await packet(reader)
            assert header == 0x10 and body[:10] == b"\x00\x04MQTT\x04\x02\x00\x1e"
            self.connections += 1
            writer.write(b"\x20\x02\x00\x00")
            await writer.drain()
            while True:
                header, body = await packet(reader)
                if header >> 4 == 3:
                    length = struct.unpack("!H", body[:2])[0]
                    self.messages.append(
                        (body[2 : 2 + length].decode(), json.loads(body[2 + length :]), bool(header & 1))
                    )
                elif header == 0xC0:
                    writer.write(b"\xd0\x00")
                    await writer.drain()
                elif header == 0xE0:
                    return
                else:
                    raise AssertionError(f"Unexpected MQTT packet {header}")
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()
            self.tasks.discard(task)

    async def start(self, tls=None):
        self.server = await asyncio.start_server(self.serve, "127.0.0.1", 0, ssl=tls)
        self.url = f"{'mqtts' if tls else 'mqtt'}://127.0.0.1:{self.server.sockets[0].getsockname()[1]}"

    async def close(self):
        self.server.close()
        await self.server.wait_closed()
        for client in self.clients:
            client.close()
        for task in list(self.tasks):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


async def wait_for(predicate):
    async with asyncio.timeout(8):
        while not predicate():
            await asyncio.sleep(0.02)


def config(url):
    return {
        "enabled": True,
        "publisher_id": "publisher-test",
        "broker_url": url,
        "publishing_interval_ms": 50,
        "writers": [
            {
                "writer_id": 1,
                "name": "power",
                "topic": "test/power",
                "metadata_topic": "test/power/meta",
                "key_frame_count": 3,
                "fields": [{"node_id": NODE, "alias": "Power"}],
            },
            {
                "writer_id": 2,
                "name": "events",
                "kind": "events",
                "topic": "test/events",
                "metadata_topic": "test/events/meta",
                "source_nodes": ["i=2253"],
            },
        ],
    }


@pytest.mark.asyncio
async def test_real_mqtt_values_events_reconnect_and_stop():
    broker = Broker()
    await broker.start()
    publisher_config = config(broker.url)
    server = OpcUaServer(
        "127.0.0.1",
        free_port(),
        "urn:test:pubsub",
        definitions=[DEFINITION],
        features={"pubsub": publisher_config, "events": {"enabled": True}},
    )
    try:
        await server.start()
        await wait_for(lambda: any(topic == "test/power" for topic, _, _ in broker.messages))
        metadata = next(
            message for topic, message, retained in broker.messages if topic == "test/power/meta" and retained
        )
        assert metadata["MessageType"] == "ua-metadata"
        assert metadata["MetaData"]["Fields"][0]["BuiltInType"] == 11
        message = next(message for topic, message, _ in broker.messages if topic == "test/power")
        assert message["PublisherId"] == "publisher-test" and message["MessageType"] == "ua-data"
        assert message["Messages"][0]["Payload"]["Power"]["Value"] == {"Type": 11, "Body": 12.5}
        assert message["Messages"][0]["Payload"]["Power"]["StatusCode"] == 0
        await server.write(NODE, 77.0)
        await wait_for(
            lambda: any(
                m["Messages"][0]["Payload"].get("Power", {}).get("Value", {}).get("Body") == 77.0
                for topic, m, _ in broker.messages
                if topic == "test/power"
            )
        )
        await wait_for(
            lambda: any(
                m["Messages"][0]["MessageType"] == "ua-deltaframe"
                for topic, m, _ in broker.messages
                if topic == "test/power"
            )
        )
        await server.emit_event("Alarm", 800)
        await wait_for(lambda: any(topic == "test/events" for topic, _, _ in broker.messages))
        event = next(m for topic, m, _ in broker.messages if topic == "test/events")["Messages"][0]
        assert event["MessageType"] == "ua-event"
        assert event["Payload"]["Message"] == {"Type": 21, "Body": {"Text": "Alarm"}}
        assert event["Payload"]["Severity"] == {"Type": 5, "Body": 800}
        broker.clients[-1].close()
        await wait_for(lambda: broker.connections >= 2)
        await wait_for(lambda: len([1 for topic, _, _ in broker.messages if topic == "test/power/meta"]) == 2)
        second_metadata = [i for i, (topic, _, _) in enumerate(broker.messages) if topic == "test/power/meta"][1]
        await wait_for(lambda: any(topic == "test/power" for topic, _, _ in broker.messages[second_metadata + 1 :]))
        resumed = next(m for topic, m, _ in broker.messages[second_metadata + 1 :] if topic == "test/power")
        assert resumed["Messages"][0]["MessageType"] == "ua-keyframe"
        status = next(c["details"] for c in server.capabilities() if c["name"] == "pubsub")
        assert status["connected"] and status["published_count"] > 0
        await server.configure_feature("pubsub", {**publisher_config, "enabled": False})
        count = len(broker.messages)
        await asyncio.sleep(0.15)
        assert len(broker.messages) == count
        assert not next(c["details"] for c in server.capabilities() if c["name"] == "pubsub")["connected"]
    finally:
        await server.stop()
        await broker.close()


@pytest.mark.asyncio
async def test_idle_event_writer_detects_disconnect_and_reconnects_without_waiting_interval():
    broker = Broker()
    await broker.start()
    publishing = config(broker.url)
    publishing["writers"] = publishing["writers"][1:]
    publishing["publishing_interval_ms"] = 60_000
    server = OpcUaServer(
        "127.0.0.1",
        free_port(),
        "urn:test:idle",
        features={
            "pubsub": publishing,
            "events": {"enabled": True},
        },
    )
    try:
        await server.start()
        await wait_for(lambda: broker.messages)
        broker.clients[-1].close()
        await wait_for(lambda: broker.connections >= 2)
        assert len([1 for topic, _, _ in broker.messages if topic.endswith("/meta")]) == 2
    finally:
        await server.stop()
        await broker.close()


@pytest.mark.asyncio
async def test_cancel_during_connect_closes_socket_and_publisher_can_be_reused():
    received, closed, acknowledge = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def delayed(reader, writer):
        try:
            await packet(reader)
            received.set()
            await acknowledge.wait()
            writer.write(b"\x20\x02\x00\x00")
            await writer.drain()
            await reader.read()
            closed.set()
        finally:
            writer.close()

    listener = await asyncio.start_server(delayed, "127.0.0.1", 0)
    publisher = MqttPublisher()

    async def connecting():
        async with publisher.connection(f"mqtt://127.0.0.1:{listener.sockets[0].getsockname()[1]}", "cancel"):
            await asyncio.Event().wait()

    task = asyncio.create_task(connecting())
    try:
        await asyncio.wait_for(received.wait(), 5)
        task.cancel()
        acknowledge.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
        await asyncio.wait_for(closed.wait(), 5)
        assert not publisher.connected
        broker = Broker()
        await broker.start()
        try:
            async with publisher.connection(broker.url, "reused"):
                await publisher.publish("test/reused", b"{}")
                await wait_for(lambda: broker.messages)
            assert not publisher.connected
        finally:
            await broker.close()
    finally:
        acknowledge.set()
        listener.close()
        await listener.wait_closed()


@pytest.mark.asyncio
async def test_reconfigure_closes_previous_broker_and_channels_remain_isolated():
    old, new = Broker(), Broker()
    await old.start()
    await new.start()
    first = OpcUaServer(
        "127.0.0.1", free_port(), "urn:test:first", definitions=[DEFINITION], features={"pubsub": config(old.url)}
    )
    second = OpcUaServer(
        "127.0.0.1",
        free_port(),
        "urn:test:second",
        definitions=[DEFINITION],
        features={"pubsub": {**config(old.url), "publisher_id": "second"}},
    )
    try:
        await first.start()
        await second.start()
        await wait_for(
            lambda: (
                {m.get("PublisherId") for topic, m, _ in old.messages if topic == "test/power"}
                == {
                    "publisher-test",
                    "second",
                }
            )
        )
        await first.configure_feature("pubsub", config(new.url))
        await wait_for(lambda: any(topic == "test/power" for topic, _, _ in new.messages))
        count = len(old.messages)
        await second.write(NODE, 9.0)
        await wait_for(lambda: len(old.messages) > count + 1)
        assert all(m.get("PublisherId") == "second" for _, m, _ in old.messages[count:])
    finally:
        await first.stop()
        await second.stop()
        await old.close()
        await new.close()


@pytest.mark.asyncio
async def test_mqtt_tls_checks_trust_and_publishes_with_trusted_certificate(tmp_path, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip_address("127.0.0.1"))]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(cert_path, key_path)
    broker = Broker()
    await broker.start(tls)
    publisher = MqttPublisher()
    try:
        with pytest.raises(aiomqtt.MqttError, match="CERTIFICATE_VERIFY_FAILED"):
            async with publisher.connection(broker.url, "untrusted"):
                pytest.fail("Untrusted certificate accepted")
        assert not publisher.connected
        monkeypatch.setenv("SSL_CERT_FILE", str(cert_path))
        async with publisher.connection(broker.url, "trusted"):
            await publisher.publish("tls/data", b'{"value":1}')
            await wait_for(lambda: broker.messages)
            assert broker.messages[0][1] == {"value": 1}
    finally:
        await broker.close()


@pytest.mark.asyncio
async def test_failed_broker_does_not_stop_ua_server():
    server = OpcUaServer(
        "127.0.0.1",
        free_port(),
        "urn:test:pubsub:failure",
        definitions=[DEFINITION],
        features={"pubsub": config(f"mqtt://127.0.0.1:{free_port()}")},
    )
    try:
        await server.start()
        await wait_for(lambda: next(c["details"] for c in server.capabilities() if c["name"] == "pubsub")["error"])
        assert server.running and (await server.read(NODE))["value"] == 12.5
        assert not next(c["details"] for c in server.capabilities() if c["name"] == "pubsub")["connected"]
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_mqtt_rejected_connack_and_long_remaining_length():
    async def reject(reader, writer):
        await packet(reader)
        writer.write(b"\x20\x02\x00\x05")
        await writer.drain()
        writer.close()

    listener = await asyncio.start_server(reject, "127.0.0.1", 0)
    publisher = MqttPublisher()
    try:
        with pytest.raises(aiomqtt.MqttError):
            async with publisher.connection(f"mqtt://127.0.0.1:{listener.sockets[0].getsockname()[1]}", "test"):
                pytest.fail("Rejected connection entered the context")
        assert not publisher.connected
    finally:
        listener.close()
        await listener.wait_closed()
    broker = Broker()
    await broker.start()
    try:
        async with publisher.connection(broker.url, "test"):
            await publisher.publish("long/topic", json.dumps({"text": "字" * 1000}).encode())
            await wait_for(lambda: broker.messages)
            assert broker.messages[0][1]["text"] == "字" * 1000
        assert not publisher.connected
    finally:
        await broker.close()


@pytest.mark.asyncio
async def test_node_capabilities_and_multiple_event_sources(tmp_path):
    server = OpcUaServer(
        "127.0.0.1",
        free_port(),
        "urn:test:sources",
        definitions=[DEFINITION],
        features={"history": {"enabled": True, "nodes": [NODE]}, "history_path": str(tmp_path / "history.sqlite")},
    )
    client = OpcUaClient(server.endpoint_url)
    try:
        await server.start()
        source = await server._core._server.nodes.objects.add_object("ns=2;s=events", "Events")
        await server.configure_feature(
            "events", {"enabled": True, "source_nodes": ["i=2253", source.nodeid.to_string()]}
        )
        await client.start()
        capability = await client.node_capabilities(NODE)
        assert capability["node_class"] == "Variable" and capability["history_read"] and capability["historizing"]
        assert (await client.node_capabilities("i=2253"))["event_notifier"]
        assert (await client.node_capabilities("ns=2;s=events"))["event_notifier"]
        await client.configure_feature(
            "events",
            {
                "enabled": True,
                "source_nodes": ["i=2253", "ns=2;s=events"],
                "minimum_severity": 500,
                "message_filter": "alarm",
            },
        )
        await server.emit_event("ignore", 800, "i=2253")
        await server.emit_event("Alarm A", 800, "i=2253")
        await server.emit_event("Alarm B", 800, "ns=2;s=events")
        await wait_for(lambda: len([e for e in client.stream.page()["events"] if e["kind"] == "event"]) == 2)
        assert {e["SourceNode"] for e in client.stream.page()["events"] if e["kind"] == "event"} == {
            "i=2253",
            "ns=2;s=events",
        }
        with pytest.raises(ValueError, match="Object"):
            await server.configure_feature("events", {"enabled": True, "source_nodes": [NODE]})
        await server.emit_event("Alarm restored", 800)
        await wait_for(lambda: any(e.get("Message") == "Alarm restored" for e in client.stream.page()["events"]))
        start = datetime.now(UTC) - timedelta(minutes=1)
        page = await client.read_history(NODE, start, datetime.now(UTC), 1)
        if page["continuation"]:
            released = await client.read_history(NODE, start, datetime.now(UTC), 1, page["continuation"], release=True)
            assert released["values"] == []
    finally:
        await client.stop()
        await server.stop()


@pytest.mark.parametrize(
    "changes",
    [
        {"broker_url": "http://localhost:1883"},
        {"broker_url": "mqtt://user:password@localhost"},
        {"writers": [{"writer_id": 1, "name": "a", "topic": "a/#", "metadata_topic": "meta"}]},
        {
            "writers": [
                {
                    "writer_id": 1,
                    "name": "a",
                    "topic": "a",
                    "metadata_topic": "meta",
                    "fields": [{"node_id": "i=1", "alias": "x"}, {"node_id": "i=2", "alias": "x"}],
                }
            ]
        },
    ],
)
def test_invalid_pubsub_configs_are_rejected(changes):
    with pytest.raises(ValidationError):
        PubSubConfig.model_validate({**config("mqtt://127.0.0.1:1883"), **changes})


@pytest.mark.asyncio
async def test_processed_history_pages_preserve_native_cursor_and_bound_intervals(monkeypatch):
    requests = []

    async def history_read(params):
        requests.append(params)
        return [
            ua.HistoryReadResult(
                HistoryData=ua.HistoryData(
                    DataValues=[
                        ua.DataValue(
                            ua.Variant(42.0, ua.VariantType.Double),
                            SourceTimestamp=params.HistoryReadDetails.StartTime,
                            ServerTimestamp=datetime.now(UTC),
                        )
                    ]
                ),
                ContinuationPoint=b"native" if len(requests) == 1 else None,
            )
        ]

    core = UaClientCore("opc.tcp://127.0.0.1:4840/ems/")
    node = SimpleNamespace(nodeid=ua.NodeId.from_string(NODE), session=SimpleNamespace(history_read=history_read))
    monkeypatch.setattr(core, "_node", lambda _: node)
    start = datetime.now(UTC)
    end = start + timedelta(seconds=5)
    first = await core.read_history(NODE, start, end, 2, mode="processed", timestamps="Source")
    assert requests[0].HistoryReadDetails.EndTime == start + timedelta(seconds=2)
    assert first["values"][0]["server_timestamp"] is None
    second = await core.read_history(NODE, start, end, 2, first["continuation"], mode="processed", timestamps="Source")
    assert requests[1].NodesToRead[0].ContinuationPoint == b"native"
    assert requests[1].HistoryReadDetails.StartTime == start
    third = await core.read_history(NODE, start, end, 2, second["continuation"], mode="processed", timestamps="Source")
    assert requests[2].HistoryReadDetails.StartTime == start + timedelta(seconds=2)
    assert requests[2].HistoryReadDetails.EndTime == start + timedelta(seconds=4)
    before = len(requests)
    released = await core.read_history(
        NODE, start, end, 2, third["continuation"], True, mode="processed", timestamps="Source"
    )
    assert len(requests) == before and released["continuation"] is None
    with pytest.raises(ValueError, match="查询不匹配"):
        await core.read_history(
            NODE, start, end, 2, third["continuation"], mode="processed", aggregate="Maximum", timestamps="Source"
        )
