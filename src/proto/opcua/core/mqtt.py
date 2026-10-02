"""Bounded aiomqtt adapter; MQTT framing, sockets and keepalive belong to the library."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager, suppress
import ssl
from urllib.parse import urlsplit

import aiomqtt


class MqttPublisher:
    def __init__(self):
        self._client: aiomqtt.Client | None = None
        self._connected = False
        self._disconnected = asyncio.Event()
        self.error: str | None = None

    @property
    def connected(self) -> bool:
        return self._connected and self.error is None

    @asynccontextmanager
    async def connection(self, url: str, client_id: str) -> AsyncIterator["MqttPublisher"]:
        if self._client is not None:
            raise RuntimeError("MQTT 连接上下文不可重入")
        parsed = urlsplit(url)
        if parsed.scheme not in {"mqtt", "mqtts"} or not parsed.hostname:
            raise ValueError("Broker 地址应为 mqtt://host:port 或 mqtts://host:port")
        tls = ssl.create_default_context() if parsed.scheme == "mqtts" else None
        client = aiomqtt.Client(
            hostname=parsed.hostname,
            port=parsed.port or (8883 if tls else 1883),
            identifier=client_id,
            protocol=aiomqtt.ProtocolVersion.V311,
            clean_session=True,
            keepalive=30,
            timeout=5,
            tls_context=tls,
            max_queued_incoming_messages=1,
            max_queued_outgoing_messages=1,
            max_concurrent_outgoing_calls=1,
        )
        self._client = client
        self.error = None
        self._disconnected.clear()
        try:
            async with AsyncExitStack() as stack:
                # Failed/cancelled CONNACK waits must also close any socket that
                # Paho's executor created, so register cleanup before entering.
                stack.push_async_exit(client)
                entering = asyncio.create_task(client.__aenter__())
                try:
                    await asyncio.shield(entering)
                except asyncio.CancelledError:
                    # Await the library timeout instead of cancelling a blocking
                    # connect worker halfway through and leaking its later socket.
                    with suppress(aiomqtt.MqttError, OSError):
                        await entering
                    raise
                self._connected = True
                watcher = asyncio.create_task(self._watch(client), name="opcua-mqtt-disconnect")
                try:
                    yield self
                finally:
                    self._connected = False
                    watcher.cancel()
                    with suppress(asyncio.CancelledError):
                        await watcher
        except (aiomqtt.MqttError, OSError) as exc:
            self.error = str(exc) or type(exc).__name__
            raise
        finally:
            self._connected = False
            self._client = None
            self._disconnected.set()

    async def _watch(self, client: aiomqtt.Client) -> None:
        # The public iterator also reports disconnects for publish-only clients,
        # including idle event writers with nothing to publish.
        try:
            async for _ in client.messages:
                pass
        except (aiomqtt.MqttError, OSError) as exc:
            self.error = str(exc) or type(exc).__name__
            self._connected = False
            self._disconnected.set()

    async def wait_for_disconnect(self, timeout: float) -> bool:
        try:
            async with asyncio.timeout(timeout):
                await self._disconnected.wait()
            return True
        except TimeoutError:
            return False

    async def publish(self, topic: str, payload: bytes, retained: bool = False) -> None:
        if not topic or any(c in topic for c in ("#", "+", "\x00")):
            raise ValueError("MQTT 发布主题无效")
        if len(topic.encode("utf-8")) + len(payload) > 4 * 1024 * 1024:
            raise ValueError("MQTT 消息超过 4 MiB")
        if not self.connected or self._client is None:
            raise aiomqtt.MqttError(self.error or "MQTT 未连接")
        try:
            await self._client.publish(topic, payload, qos=0, retain=retained, timeout=5)
        except aiomqtt.MqttError as exc:
            self.error = str(exc) or type(exc).__name__
            self._connected = False
            self._disconnected.set()
            raise
