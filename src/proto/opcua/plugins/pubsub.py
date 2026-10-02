"""Channel-owned variable / event publishers; no SDK objects escape the core."""

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
import json
from uuid import NAMESPACE_URL, uuid4, uuid5

import aiomqtt

from src.proto.opcua.core.feature_config import PubSubConfig
from src.proto.opcua.core.mqtt import MqttPublisher
from src.proto.opcua.core.pubsub_json import EVENT_TYPES, data_value, field_metadata, overall_status, variant
from src.proto.opcua.plugins.base import PluginContext


class PubSubPlugin:
    def __init__(self):
        self._task = None
        self._mqtt = MqttPublisher()
        self._error = None
        self._published = 0
        self._last_publish = None
        self._writers = {}
        self._cursor = 0
        self._sequence = {}
        self._previous = {}
        self._stopping = False

    async def initialize(self, context: PluginContext) -> None:
        self._config = PubSubConfig.model_validate(context.config.get("pubsub", {}))
        self._port, self._stream, self._channel = context.ua_port, context.event_sink, context.channel_id
        self._events_config = dict(context.config.get("events", {}))
        if self._port is None or self._stream is None:
            raise ValueError("发布器缺少节点读取接口或事件流")
        nodes = {node["node_id"] for node in context.config.get("definitions", [])}
        if any(f.node_id not in nodes for w in self._config.writers for f in w.fields):
            raise ValueError("发布数据集包含不存在的变量")

    async def start(self) -> None:
        if self._config.enabled:
            self._stopping = False
            # Do not replay old events when a publisher is enabled/reconfigured.
            self._cursor = self._stream.page()["latest_sequence"]
            self._task = asyncio.create_task(self._run(), name=f"opcua-pubsub-{self._channel}")

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def status(self) -> dict:
        return {
            "enabled": self._config.enabled,
            "connected": self._mqtt.connected,
            "error": self._error or self._mqtt.error,
            "published_count": self._published,
            "last_publish": self._last_publish,
            "writers": self._writers,
        }

    def configure_events(self, config: dict) -> None:
        self._events_config = dict(config)

    async def _send(self, topic: str, message: dict, retained: bool = False) -> None:
        await self._mqtt.publish(
            topic, json.dumps(message, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode(), retained
        )

    async def _metadata(self, writer) -> None:
        fields = []
        if writer.kind == "variables":
            for field in writer.fields:
                snapshot = await self._port.read(field.node_id)
                fields.append(
                    field_metadata(
                        field.alias,
                        snapshot.get("variant_type"),
                        str(uuid5(NAMESPACE_URL, f"{self._channel}/{writer.writer_id}/{field.node_id}")),
                        isinstance(snapshot.get("value"), list),
                    )
                )
        else:
            for name in writer.event_fields:
                fields.append(
                    field_metadata(name, EVENT_TYPES[name], str(uuid5(NAMESPACE_URL, f"{writer.writer_id}/{name}")))
                )
        await self._send(
            writer.metadata_topic,
            {
                "MessageId": str(uuid4()),
                "MessageType": "ua-metadata",
                "PublisherId": self._config.publisher_id,
                "DataSetWriterId": writer.writer_id,
                "DataSetWriterName": writer.name,
                "WriterGroupName": self._config.writer_group_name,
                "Timestamp": datetime.now(UTC).isoformat(),
                "MetaData": {
                    "Name": writer.name,
                    "Fields": fields,
                    "DataSetClassId": "00000000-0000-0000-0000-000000000000",
                    "ConfigurationVersion": {"MajorVersion": self._config.config_version, "MinorVersion": 0},
                },
            },
            True,
        )

    async def _message(self, writer, payload: dict, message_type: str, status: int = 0) -> None:
        number = self._sequence.get(writer.writer_id, 0)
        message = {"DataSetWriterId": writer.writer_id, "MessageType": message_type, "Payload": payload}
        content = self._config.message_content
        if "sequence_number" in content:
            message["SequenceNumber"] = number
        if "timestamp" in content:
            message["Timestamp"] = datetime.now(UTC).isoformat()
        if "status" in content:
            message["Status"] = status
        if "metadata_version" in content:
            message["MetaDataVersion"] = {"MajorVersion": self._config.config_version, "MinorVersion": 0}
        network = {"MessageId": str(uuid4()), "MessageType": "ua-data", "Messages": [message]}
        if "publisher_id" in content:
            network["PublisherId"] = self._config.publisher_id
        if "writer_group_name" in content:
            network["WriterGroupName"] = self._config.writer_group_name
        await self._send(writer.topic, network)
        self._sequence[writer.writer_id] = (number + 1) & 0xFFFFFFFF
        self._published += 1
        self._last_publish = datetime.now(UTC).isoformat()
        self._writers[str(writer.writer_id)] = {
            "published_count": self._sequence[writer.writer_id],
            "error": None,
            "last_publish": self._last_publish,
        }

    async def _variables(self, writer) -> None:
        snapshots, payload = [], {}
        for field in writer.fields:
            snapshot = await self._port.read(field.node_id)
            snapshots.append(snapshot)
            payload[field.alias] = data_value(snapshot, self._config.field_content)
        previous = self._previous.get(writer.writer_id)
        keyframe = previous is None or self._sequence.get(writer.writer_id, 0) % writer.key_frame_count == 0
        changed = payload if keyframe else {key: value for key, value in payload.items() if previous.get(key) != value}
        await self._message(writer, changed, "ua-keyframe" if keyframe else "ua-deltaframe", overall_status(snapshots))
        self._previous[writer.writer_id] = payload
        for snapshot in snapshots:
            await self._stream.emit({"kind": "value", "source": "pubsub", "writer_id": writer.writer_id, **snapshot})

    async def _events(self, writer, events: list[dict]) -> None:
        if not self._events_config.get("enabled"):
            raise ValueError("事件功能未启用，无法发布事件数据集")
        for event in events:
            sources = {key.removeprefix("ns=0;") for key in writer.source_nodes}
            if event.get("kind") != "event" or str(event.get("SourceNode")).removeprefix("ns=0;") not in sources:
                continue
            if event.get("Severity", 0) < self._events_config.get("minimum_severity", 0):
                continue
            if self._events_config.get("message_filter", "").casefold() not in str(event.get("Message", "")).casefold():
                continue
            payload = {name: variant(event.get(name), EVENT_TYPES[name]) for name in writer.event_fields}
            await self._message(writer, payload, "ua-event")

    async def _run(self) -> None:
        delay = 1
        writers = [
            w for w in self._config.writers if w.enabled and (w.fields if w.kind == "variables" else w.source_nodes)
        ]
        while not self._stopping:
            try:
                async with self._mqtt.connection(self._config.broker_url, f"ems-{self._channel}-{uuid4().hex[:12]}"):
                    self._previous.clear()
                    for writer in writers:
                        await self._metadata(writer)
                    delay = 1
                    while not self._stopping:
                        page = self._stream.page(self._cursor, limit=2000)
                        self._error = "事件流已溢出，部分事件未发布" if page["gap"] else None
                        for writer in writers:
                            try:
                                if writer.kind == "variables":
                                    await self._variables(writer)
                                else:
                                    await self._events(writer, page["events"])
                            except (aiomqtt.MqttError, OSError, TimeoutError):
                                raise
                            except Exception as exc:
                                self._writers[str(writer.writer_id)] = {"error": str(exc), "last_publish": None}
                        if page["events"]:
                            self._cursor = page["events"][-1]["sequence"]
                        else:
                            self._cursor = page["latest_sequence"]
                        if await self._mqtt.wait_for_disconnect(self._config.publishing_interval_ms / 1000):
                            raise aiomqtt.MqttError(self._mqtt.error or "MQTT 连接已断开")
            except (aiomqtt.MqttError, OSError, TimeoutError) as exc:
                self._error = str(exc) or type(exc).__name__
                if self._stopping:
                    return
                await asyncio.sleep(delay)
                delay = min(30, delay * 2)
            except Exception as exc:
                # Invalid local metadata/configuration cannot heal by reconnecting.
                self._error = str(exc) or type(exc).__name__
                return
