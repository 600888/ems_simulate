"""Reliable asynchronous DNP3 Master adapter."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import ssl
import time
from typing import Any

from pydnp3_pure.app.constants import IIN2, CommandStatus, FunctionCode, PointFlags, Qualifier
from pydnp3_pure.app.fragment import AppMessage, ObjectData, build_request
from pydnp3_pure.app.header import AppControl
from pydnp3_pure.app.layer import ApplicationLayer
from pydnp3_pure.app.object_header import ObjectHeader
from pydnp3_pure.link.frame import LinkFrame
from pydnp3_pure.link.layer import LinkLayer
from pydnp3_pure.objects.types import CROB, AnalogOutputCommand, DNP3Timestamp
from pydnp3_pure.transport.layer import TransportLayer

from src.config.config import Config
from src.device.core.message.message_capture import MessageCapture
from src.proto.dnp3.objects import DelayValue
from src.proto.dnp3.point_config import Dnp3PointConfig
from src.proto.dnp3.reliable_link import LINK_STATUS, ReliableLinkEndpoint
from src.proto.dnp3.tracked_tcp_client import TrackedTcpClient
from src.proto.dnp3.wire import FragmentCorrelator, WireFrameExtractor, accepts_link_address

_STATIC_VARIATIONS = {1: 2, 10: 2, 30: 5, 40: 3}


class Dnp3RequestError(RuntimeError):
    """A request was sent but did not complete successfully."""


@dataclass(slots=True)
class PendingRequest:
    sequence: int
    function: FunctionCode
    objects: tuple[tuple[int, int, int, int], ...]
    sent_at: float
    attempt: int
    future: asyncio.Future[AppMessage]


class _MasterHandler:
    """Cache complete point metadata instead of only the latest scalar value."""

    def __init__(self) -> None:
        self._values: dict[tuple[int, int], Any] = {}
        self._metadata: dict[tuple[int, int], dict[str, Any]] = {}

    def update(self, message: AppMessage, *, source: str) -> list[tuple[int, int, Any]]:
        """将响应报文写入缓存，并返回本次更新的 ``(group, index, value)``。"""
        received_at = time.time()
        updates: list[tuple[int, int, Any]] = []
        for obj in message.objects:
            group = obj.header.group
            for ordinal, point in enumerate(obj.points):
                if isinstance(point, tuple) and len(point) == 2:
                    index, value_source = point
                else:
                    index = getattr(point, "index", obj.header.start + ordinal)
                    value_source = point
                value = getattr(value_source, "value", value_source)
                key = (group, int(index))
                self._values[key] = value
                updates.append((group, int(index), value))
                self._metadata[key] = {
                    "group": group,
                    "variation": obj.header.variation,
                    "index": int(index),
                    "value": value,
                    "flags": getattr(value_source, "flags", None),
                    "timestamp": getattr(value_source, "timestamp", None),
                    "received_at": received_at,
                    "source": source,
                    "valid": True,
                    "communication_lost": False,
                }
        return updates

    def mark_communication_lost(self) -> None:
        """将所有缓存测点标记为通信中断，品质转无效。"""
        for metadata in self._metadata.values():
            metadata["valid"] = False
            metadata["communication_lost"] = True


class Dnp3Client:
    """DNP3 Master with response matching, timeout/retry and reconnect support."""

    def __init__(self, log=None):
        self._log = log
        self._client: TrackedTcpClient | None = None
        self._ssl_context: ssl.SSLContext | None = None
        self._handler = _MasterHandler()
        self._is_running = False
        self._desired_running = False
        self._config: dict[str, Any] = {}
        self._capture = MessageCapture()
        self._address = 0
        self._outstation_address = 1
        self._transport: TransportLayer | None = None
        self._link_layer: LinkLayer | None = None
        self._link_endpoint: ReliableLinkEndpoint | None = None
        self._wire_capture = WireFrameExtractor(self._capture_rx_frame)
        self._rx_fragments = FragmentCorrelator("dnp3-rx")
        self._tx_fragments = FragmentCorrelator("dnp3-tx")
        self._request_lock = asyncio.Lock()
        self._pending: dict[int, PendingRequest] = {}
        self._sequence = 0
        self._reconnect_task: asyncio.Task[None] | None = None
        self._link_status_waiter: asyncio.Future[None] | None = None
        self._transport_endpoints: tuple[object, object] | None = None
        self._on_connection_opened: Callable[..., None] | None = None
        self._on_connection_activity: Callable[..., None] | None = None
        self._on_connection_closed: Callable[..., None] | None = None
        self._on_timeout: Callable[[PendingRequest], None] | None = None
        self._on_point_update: Callable[[int, int, Any, str], None] | None = None
        self.last_error: str | None = None
        self.last_command_statuses: list[int] = []

    def _log_message(self, level: str, message: str) -> None:
        """按级别记录日志，兼容 loguru Logger 与可调用对象。"""
        if self._log is None:
            return
        method = getattr(self._log, level, None)
        if callable(method):
            method(message)
        elif callable(self._log):
            self._log(message)

    def set_addresses(self, local_addr: int, outstation_addr: int) -> None:
        """设置本端（Master）与对端（Outstation）的 DNP3 站点地址。"""
        self._address = self._validate_index(local_addr, "Master地址")
        self._outstation_address = self._validate_index(outstation_addr, "Outstation地址")

    @staticmethod
    def _validate_index(index: int, label: str = "点索引") -> int:
        """校验地址/索引必须在 0 到 65535 之间，否则抛出异常。"""
        value = int(index)
        if not 0 <= value <= 0xFFFF:
            raise ValueError(f"DNP3{label}必须在 0 到 65535 之间: {value}")
        return value

    def set_server_port(self, port: int) -> None:
        """设置对端 Outstation 的 TCP 端口。"""
        self._config["port"] = int(port)

    def set_server_ip(self, ip: str) -> None:
        """设置对端 Outstation 的 IP 地址。"""
        self._config["ip"] = ip

    def set_ssl_context(self, context: ssl.SSLContext | None) -> None:
        """Set the optional TLS context used for subsequent connections and reconnects."""
        self._ssl_context = context

    def set_parameters(self, **kwargs) -> None:
        """合并设置运行时参数（超时、重连、链路确认等）。"""
        self._config["runtime"] = {**self._config.get("runtime", {}), **kwargs}

    def set_message_capture(self, capture) -> None:
        """设置报文捕获器并重置关联的关联器。"""
        self._capture = capture if capture is not None else MessageCapture()
        self._wire_capture = WireFrameExtractor(self._capture_rx_frame)
        self._rx_fragments.reset()
        self._tx_fragments.reset()

    def set_connection_callbacks(
        self,
        *,
        on_connect=None,
        on_activity=None,
        on_disconnect=None,
        on_timeout=None,
    ) -> None:
        """注册连接打开、活动、断开及请求超时的回调。"""
        self._on_connection_opened = on_connect
        self._on_connection_activity = on_activity
        self._on_connection_closed = on_disconnect
        self._on_timeout = on_timeout

    def set_on_point_update_callback(self, callback: Callable[[int, int, Any, str], None] | None) -> None:
        """注册缓存测点更新回调，参数依次为对象组、索引、原始值和数据来源。"""
        self._on_point_update = callback

    def _notify_point_updates(self, updates: list[tuple[int, int, Any]], source: str) -> None:
        """将已解析的缓存更新通知给上层设备模型，回调异常不影响协议处理。"""
        if self._on_point_update is None:
            return
        for group, index, value in updates:
            try:
                self._on_point_update(group, index, value, source)
            except Exception as exc:
                self._log_message(
                    "error",
                    f"DNP3测点更新回调失败: group={group}, index={index}, source={source}, error={exc}",
                )

    @property
    def is_connected(self) -> bool:
        """是否已建立 TCP 连接。"""
        return bool(self._client and self._client.is_open)

    def _session_ready(self) -> bool:
        """协议栈与 TCP 连接均就绪才可发送请求。"""
        return bool(self._transport and self.is_connected)

    async def start(self) -> bool:
        """启动客户端并建立连接，失败时启动后台重连。"""
        if self._desired_running and self.is_connected:
            return True
        self._desired_running = True
        try:
            await self._connect_once()
            return True
        except (OSError, TimeoutError, ConnectionError) as exc:
            self.last_error = f"连接失败: {exc}"
            self._log_message("error", f"启动 DNP3 客户端失败: {self.last_error}")
            self._ensure_reconnect_task()
            return False

    async def _connect_once(self) -> None:
        """建立一次 TCP 连接并初始化链路/协议栈（含可选的未请求上报使能）。"""
        ip_raw = (self._config.get("ip") or "").strip()
        ip = ip_raw if ip_raw not in ("", "0.0.0.0") else "127.0.0.1"
        port = int(self._config.get("port", Config.DNP3_DEFAULT_PORT))
        runtime = self._config.get("runtime", {})
        timeout = float(runtime.get("connection_timeout_ms", 3000)) / 1000.0
        self._build_stack()
        client = TrackedTcpClient(
            ip,
            port,
            ssl_context=self._ssl_context,
            on_connect=self._handle_transport_connected,
            on_activity=self._handle_activity,
            on_disconnect=self._handle_disconnected,
        )
        client.set_receive_callback(self._on_rx)
        self._client = client
        await client.open(timeout)
        try:
            await self._verify_link_status(
                min(
                    timeout,
                    max(0.1, float(runtime.get("link_confirm_timeout_ms", 1000)) / 1000.0),
                )
            )
        except (OSError, TimeoutError, ConnectionError):
            await client.close()
            if self._client is client:
                self._client = None
            self._reset_stack()
            raise
        self._is_running = True
        self.last_error = None
        remote, local = self._transport_endpoints or (None, None)
        self._handle_connected(remote, local)
        transport = "TLS" if self._ssl_context else "TCP"
        self._log_message("info", f"DNP3 客户端已通过 {transport} 连接 {ip}:{port}")
        if self._link_endpoint and self._link_endpoint.enabled:
            self._link_endpoint.reset_remote_link(self._outstation_address, self._address)
        if bool(runtime.get("enable_unsolicited", False)):
            if not await self.enable_unsolicited(True):
                self._log_message("warning", f"DNP3启用未请求上报失败: {self.last_error}")

    async def _verify_link_status(self, timeout_seconds: float) -> None:
        """Require a DNP3 link response before reporting the device as started.

        A TCP handshake alone is insufficient: a plaintext client can complete it
        against a TLS listener and otherwise appear online until the server closes
        the socket. REQUEST_LINK_STATUS makes that mismatch fail immediately and
        also verifies that the peer is an actual DNP3 endpoint.
        """
        if not self._link_endpoint:
            raise ConnectionError("DNP3链路层未初始化")
        loop = asyncio.get_running_loop()
        waiter = loop.create_future()
        self._link_status_waiter = waiter
        try:
            self._link_endpoint.request_link_status(self._outstation_address, self._address)
            await asyncio.wait_for(waiter, timeout=timeout_seconds)
        except TimeoutError as exc:
            raise ConnectionError("DNP3链路状态确认超时") from exc
        finally:
            if self._link_status_waiter is waiter:
                self._link_status_waiter = None

    async def stop(self) -> bool:
        """停止客户端：取消重连、关闭连接并复位协议栈。"""
        self._desired_running = False
        self._is_running = False
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None
        self._fail_pending(ConnectionError("DNP3 client stopped"))
        if self._client:
            await self._client.close()
        self._client = None
        self._reset_stack()
        return True

    def is_running(self) -> bool:
        """是否处于运行且已连接状态。"""
        return self._is_running and self.is_connected

    def _build_stack(self) -> None:
        """组装传输层、应用层与可靠链路层协议栈。"""
        transport = TransportLayer(
            on_fragment=lambda _: None,
            send_frame=self._send_frame,
            local_address=self._address,
            remote_address=self._outstation_address,
        )
        application = ApplicationLayer(transport=transport, on_message=self._on_app_message)
        transport._on_fragment = application.on_fragment_received
        self._transport = transport
        self._link_layer = LinkLayer(on_frame=self._on_link_frame)
        runtime = self._config.get("runtime", {})
        self._link_endpoint = ReliableLinkEndpoint(
            enabled=bool(runtime.get("link_confirm", False)),
            local_is_master=True,
            write_frame=self._write_frame,
            deliver_frame=self._deliver_link_frame,
            timeout_seconds=float(runtime.get("link_confirm_timeout_ms", 1000)) / 1000.0,
            max_retries=int(runtime.get("link_confirm_max_retries", 2)),
            on_error=self._on_link_error,
        )
        self._wire_capture.reset()
        self._rx_fragments.reset()
        self._tx_fragments.reset()

    def _reset_stack(self) -> None:
        """复位协议栈所有层与报文关联器的状态。"""
        if self._transport:
            self._transport.reset()
        if self._link_layer:
            self._link_layer.reset()
        if self._link_endpoint:
            self._link_endpoint.reset()
        self._wire_capture.reset()
        self._rx_fragments.reset()
        self._tx_fragments.reset()

    def _on_link_frame(self, frame: LinkFrame) -> None:
        """接收链路帧：校验地址匹配后交由可靠链路端点处理。"""
        if not accepts_link_address(
            frame.header.destination,
            frame.header.source,
            local=self._address,
            remote=self._outstation_address,
        ):
            self._log_message(
                "warning",
                f"忽略地址不匹配的DNP3帧: src={frame.header.source}, dst={frame.header.destination}",
            )
            return
        if not frame.header.primary and frame.header.function == LINK_STATUS:
            waiter = self._link_status_waiter
            if waiter and not waiter.done():
                waiter.set_result(None)
        if self._link_endpoint:
            self._link_endpoint.on_frame(frame)

    def _deliver_link_frame(self, frame: LinkFrame) -> None:
        """将链路帧送入传输层处理。"""
        assert self._transport is not None
        self._transport.on_frame_received(frame)

    def _send_frame(self, frame: LinkFrame) -> None:
        """发送链路帧（启用确认时交由可靠链路端点处理）。"""
        if self._link_endpoint:
            self._link_endpoint.send(frame)
        else:
            self._write_frame(frame)

    def _write_frame(self, frame: LinkFrame) -> None:
        """将链路帧序列化并经 TCP 发送，同时记录发送报文。"""
        if not self._client or frame is None:
            raise ConnectionError("DNP3 TCP connection is unavailable")
        data = frame.serialize()
        self._capture.add_tx(data, self._tx_fragments.metadata(data))
        self._client.send(data)

    def _on_link_error(self, error: str) -> None:
        """记录可靠链路层返回的错误信息。"""
        self.last_error = error
        self._log_message("error", error)

    def _capture_rx_frame(self, raw: bytes) -> None:
        """记录接收到的原始链路帧。"""
        self._capture.add_rx(raw, self._rx_fragments.metadata(raw))

    def _on_rx(self, data: bytes) -> None:
        """处理 TCP 原始接收数据，交给链路层解析。"""
        try:
            self._wire_capture.data_received(data)
            if self._link_layer:
                self._link_layer.data_received(data)
        except Exception as exc:
            self.last_error = f"接收报文处理失败: {exc}"
            self._log_message("error", self.last_error)

    def _on_app_message(self, message: AppMessage) -> None:
        """处理应用层响应：匹配挂起请求、缓存测点并发送应用确认。"""
        control = message.header.control
        if message.function not in (FunctionCode.RESPONSE, FunctionCode.UNSOLICITED_RESPONSE):
            self._log_message(
                "warning",
                f"忽略非响应DNP3应用报文: function={message.function.name}, seq={control.seq}",
            )
            return
        if control.uns:
            updates = self._handler.update(message, source="unsolicited")
            if control.con:
                self._send_confirm(control.seq, unsolicited=True)
            self._notify_point_updates(updates, "unsolicited")
            return
        pending = self._pending.get(control.seq)
        if pending and not pending.future.done():
            requested_groups = {selector[0] for selector in pending.objects}
            response_groups = {obj.header.group for obj in message.objects}
            if (
                response_groups
                and requested_groups
                and 60 not in requested_groups
                and response_groups.isdisjoint(requested_groups)
            ):
                self._log_message(
                    "warning",
                    "忽略对象不匹配的DNP3响应: "
                    f"seq={control.seq}, requested={sorted(requested_groups)}, "
                    f"response={sorted(response_groups)}",
                )
                return
            updates = self._handler.update(message, source="solicited")
            if control.con:
                self._send_confirm(control.seq, unsolicited=False)
            self._notify_point_updates(updates, "solicited")
            pending.future.set_result(message)
        else:
            self._log_message("warning", f"收到无匹配请求的DNP3响应: seq={control.seq}")

    def _send_confirm(self, sequence: int, *, unsolicited: bool) -> None:
        """发送应用层确认（CONFIRM）帧。"""
        control = AppControl.single_fragment(seq=sequence, uns=unsolicited)
        fragment = bytes((control.to_byte(), int(FunctionCode.CONFIRM)))
        if self._transport:
            self._transport.send_fragment(fragment, direction=True)

    def _handle_transport_connected(self, remote, local) -> None:
        """Remember TCP endpoints while protocol establishment is pending."""
        self._transport_endpoints = (remote, local)

    def _handle_connected(self, remote, local) -> None:
        """协议链路确认后触发 on_connect 回调。"""
        if self._on_connection_opened:
            self._on_connection_opened(remote, local)

    def _handle_activity(self, direction: str, size: int) -> None:
        """连接收发活动时触发 on_activity 回调。"""
        if self._on_connection_activity:
            self._on_connection_activity(direction, size)

    def _handle_disconnected(self, reason: str, detail: str | None) -> None:
        """处理连接断开：标记通信丢失、失败挂起请求并按需启动重连。"""
        self._is_running = False
        self._transport_endpoints = None
        waiter = self._link_status_waiter
        if waiter and not waiter.done():
            waiter.set_exception(ConnectionError(detail or reason))
        self._handler.mark_communication_lost()
        self._fail_pending(ConnectionError(detail or reason))
        self._reset_stack()
        if self._on_connection_closed:
            self._on_connection_closed(reason, detail)
        if self._desired_running:
            self._ensure_reconnect_task()

    def _ensure_reconnect_task(self) -> None:
        """在需要且未运行时创建后台重连任务。"""
        max_attempts = int(self._config.get("runtime", {}).get("reconnect_max_attempts", 0))
        if self._desired_running and max_attempts != 0 and not self._reconnect_task:
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """按指数退避周期重连，直到成功或达到最大尝试次数。"""
        runtime = self._config.get("runtime", {})
        delay = float(runtime.get("reconnect_initial_interval_ms", 1000)) / 1000.0
        maximum = float(runtime.get("reconnect_max_interval_ms", 30000)) / 1000.0
        max_attempts = int(runtime.get("reconnect_max_attempts", 0))
        attempt = 0
        try:
            while self._desired_running and not self.is_connected:
                if max_attempts > 0 and attempt >= max_attempts:
                    self.last_error = f"DNP3重连次数已达上限: {max_attempts}"
                    self._log_message("error", self.last_error)
                    return
                await asyncio.sleep(delay)
                attempt += 1
                try:
                    await self._connect_once()
                    return
                except (OSError, TimeoutError, ConnectionError) as exc:
                    self.last_error = f"重连失败: {exc}"
                    self._log_message("warning", self.last_error)
                    delay = min(delay * 2, maximum)
        finally:
            self._reconnect_task = None

    def _fail_pending(self, error: Exception) -> None:
        """将所有挂起请求置为异常并清空。"""
        for pending in self._pending.values():
            if not pending.future.done():
                pending.future.set_exception(error)
        self._pending.clear()

    def _next_sequence(self) -> int:
        """获取下一个应用层序列号（0-15 循环）。"""
        sequence = self._sequence
        self._sequence = (self._sequence + 1) & 0x0F
        return sequence

    async def _request(self, function: FunctionCode, objects: list[ObjectData]) -> AppMessage:
        """发送请求并等待响应，支持超时重试。"""
        if not self._session_ready():
            raise ConnectionError("DNP3 client is not connected")
        runtime = self._config.get("runtime", {})
        timeout = float(runtime.get("command_timeout_ms", 3000)) / 1000.0
        retries = int(runtime.get("max_retries", 3))
        async with self._request_lock:
            sequence = self._next_sequence()
            fragment = build_request(function, sequence, objects)
            object_selectors = tuple(
                (obj.header.group, obj.header.variation, obj.header.start, obj.header.stop) for obj in objects
            )
            for attempt in range(retries + 1):
                loop = asyncio.get_running_loop()
                future: asyncio.Future[AppMessage] = loop.create_future()
                pending = PendingRequest(
                    sequence=sequence,
                    function=function,
                    objects=object_selectors,
                    sent_at=time.monotonic(),
                    attempt=attempt,
                    future=future,
                )
                self._pending[sequence] = pending
                try:
                    assert self._transport is not None
                    self._transport.send_fragment(fragment, direction=True)
                    response = await asyncio.wait_for(future, timeout)
                    self.last_error = None
                    return response
                except TimeoutError:
                    if self._on_timeout:
                        try:
                            self._on_timeout(pending)
                        except Exception as exc:
                            self._log_message("error", f"DNP3超时回调失败: {exc}")
                    if attempt >= retries:
                        self.last_error = f"DNP3请求超时: function={function.name}, seq={sequence}"
                        raise Dnp3RequestError(self.last_error) from None
                    self._log_message(
                        "warning",
                        f"DNP3请求超时，准备重试: function={function.name}, seq={sequence}, attempt={attempt + 1}",
                    )
                finally:
                    self._pending.pop(sequence, None)
        raise AssertionError("unreachable")

    @staticmethod
    def _response_ok(message: AppMessage) -> bool:
        """检查响应 IIN2 是否携带异常指示。"""
        iin = message.header.iin
        error_mask = IIN2.NO_FUNC_CODE_SUPPORT | IIN2.OBJECT_UNKNOWN | IIN2.PARAMETER_ERROR | IIN2.CONFIG_CORRUPT
        return iin is None or not bool(iin.iin2 & error_mask)

    def _response_success(self, message: AppMessage) -> bool:
        """判断响应是否成功，并维护 last_error。"""
        if self._response_ok(message):
            self.last_error = None
            return True
        iin2 = int(message.header.iin.iin2) if message.header.iin else 0
        self.last_error = f"DNP3响应IIN2异常: 0x{iin2:02X}"
        return False

    def _command_ok(self, message: AppMessage) -> bool:
        """检查控制命令响应中的 CommandStatus 是否全部成功。"""
        if not self._response_ok(message):
            iin2 = int(message.header.iin.iin2) if message.header.iin else 0
            self.last_error = f"DNP3响应IIN2异常: 0x{iin2:02X}"
            return False
        statuses: list[int] = []
        for obj in message.objects:
            for point in obj.points:
                value_source = point[1] if isinstance(point, tuple) else point
                status = getattr(value_source, "status", None)
                if status is not None:
                    statuses.append(int(status))
        self.last_command_statuses = statuses
        if not statuses:
            self.last_error = "DNP3控制响应未包含命令状态"
            return False
        if any(status != 0 for status in statuses):
            descriptions = []
            for status in statuses:
                try:
                    name = CommandStatus(status).name
                except ValueError:
                    name = "UNKNOWN"
                descriptions.append(f"{name}({status})")
            self.last_error = f"DNP3控制失败，CommandStatus={', '.join(descriptions)}"
            return False
        self.last_error = None
        return True

    async def send_integrity_poll(self) -> bool:
        """发送 Class 0 完整性轮询并判断响应是否成功。"""
        obj = ObjectData(ObjectHeader(60, 1, Qualifier.ALL_POINTS, 0, 0, 0))
        try:
            return self._response_success(await self._request(FunctionCode.READ, [obj]))
        except (ConnectionError, Dnp3RequestError, ValueError) as exc:
            self.last_error = str(exc)
            return False

    async def send_event_poll(self, classes: tuple[int, ...] = (1, 2, 3)) -> bool:
        """发送事件轮询并按类读取事件，判断响应是否成功。"""
        objects = [ObjectData(ObjectHeader(60, number + 1, Qualifier.ALL_POINTS, 0, 0, 0)) for number in classes]
        try:
            return self._response_success(await self._request(FunctionCode.READ, objects))
        except (ConnectionError, Dnp3RequestError, ValueError) as exc:
            self.last_error = str(exc)
            return False

    def read_analog(self, index: int) -> Any:
        """读取缓存的模拟量输入（G30）。"""
        return self.read_point(index, 30)

    def read_binary(self, index: int) -> Any:
        """读取缓存的二进制输入（G1）。"""
        return self.read_point(index, 1)

    def read_point(self, index: int, group: int, frame_type: int = 0) -> Any:
        """从缓存读取测点值，可带 TTL 有效性判断。"""
        key = (group, index)
        metadata = self._handler._metadata.get(key)
        if not metadata or not metadata.get("valid"):
            return None
        ttl_ms = int(self._config.get("runtime", {}).get("cache_ttl_ms", 0))
        if ttl_ms > 0 and (time.time() - float(metadata["received_at"])) * 1000 > ttl_ms:
            metadata["valid"] = False
            metadata["stale"] = True
            return None
        return self._handler._values.get(key)

    def read_point_metadata(self, index: int, group: int) -> dict[str, Any] | None:
        """读取测点完整元数据，解析品质位并附加缓存年龄。"""
        metadata = self._handler._metadata.get((group, index))
        if metadata is None:
            return None
        result = dict(metadata)
        flags = result.get("flags")
        if flags is not None:
            raw = int(flags)
            result["quality"] = {
                "online": bool(raw & PointFlags.ONLINE),
                "restart": bool(raw & PointFlags.RESTART),
                "communication_lost": bool(raw & PointFlags.COMM_LOST),
                "remote_forced": bool(raw & PointFlags.REMOTE_FORCED),
                "local_forced": bool(raw & PointFlags.LOCAL_FORCED),
                "over_range": bool(raw & PointFlags.OVER_RANGE),
                "reference_error": bool(raw & PointFlags.REFERENCE_ERR),
                "raw": raw,
            }
        result["age_ms"] = max(0, int((time.time() - float(result["received_at"])) * 1000))
        ttl_ms = int(self._config.get("runtime", {}).get("cache_ttl_ms", 0))
        if ttl_ms > 0 and result["age_ms"] > ttl_ms:
            result["valid"] = False
            result["stale"] = True
        return result

    async def read_point_active(self, index: int, group: int, variation: int | None = None) -> Any:
        """主动发送读请求获取单点最新值，并刷新本地缓存。"""
        if not 0 <= index <= 0xFFFF:
            return None
        variation = variation or _STATIC_VARIATIONS.get(group, 0)
        header = ObjectHeader(group, variation, Qualifier.RANGE_16_START_STOP, index, index, 1)
        try:
            response = await self._request(FunctionCode.READ, [ObjectData(header)])
            if not self._response_success(response):
                return None
            return self.read_point(index, group)
        except (ConnectionError, Dnp3RequestError, ValueError) as exc:
            self.last_error = str(exc)
            return None

    async def read_points_active(self, points: Sequence[tuple[int, int]]) -> dict[tuple[int, int], Any]:
        """主动批量读取多个测点：按组压缩为连续区间并一次性请求。"""
        if not points:
            return {}
        grouped: dict[int, list[int]] = {}
        for index, group in points:
            if not 0 <= index <= 0xFFFF:
                self.last_error = f"DNP3点索引超出范围: {index}"
                return {}
            grouped.setdefault(group, []).append(index)
        objects: list[ObjectData] = []
        for group, indexes in grouped.items():
            ordered = sorted(set(indexes))
            run_start = run_stop = ordered[0]
            for index in ordered[1:] + [None]:
                if index is not None and index == run_stop + 1:
                    run_stop = index
                    continue
                qualifier = Qualifier.RANGE_8_START_STOP if run_stop <= 0xFF else Qualifier.RANGE_16_START_STOP
                objects.append(
                    ObjectData(
                        ObjectHeader(
                            group,
                            _STATIC_VARIATIONS.get(group, 0),
                            qualifier,
                            run_start,
                            run_stop,
                            run_stop - run_start + 1,
                        )
                    )
                )
                if index is not None:
                    run_start = run_stop = index
        try:
            response = await self._request(FunctionCode.READ, objects)
        except (ConnectionError, Dnp3RequestError, ValueError) as exc:
            self.last_error = str(exc)
            return {}
        if not self._response_success(response):
            return {}
        return {(index, group): self.read_point(index, group) for index, group in points}

    @staticmethod
    def _index_qualifier(index: int) -> Qualifier:
        """根据索引大小选择 8 位或 16 位索引限定词。"""
        if not 0 <= index <= 0xFFFF:
            raise ValueError("DNP3 point index must be between 0 and 65535")
        return Qualifier.INDEX_8 if index <= 0xFF else Qualifier.INDEX_16

    async def write_analog(self, index: int, value: float) -> bool:
        """直接操作写模拟量输出（数字直接操作，无双态选择）。"""
        return await self.operate_analog(index, value, sbo=False)

    async def _analog_operation(
        self,
        function: FunctionCode,
        index: int,
        value: float,
        variation: int = 3,
    ) -> bool:
        """执行模拟量输出命令并返回命令状态是否成功。"""
        try:
            command = AnalogOutputCommand(index=index, value=float(value), status=0)
            header = ObjectHeader(41, variation, self._index_qualifier(index), 0, 0, 1)
            response = await self._request(function, [ObjectData(header, [command])])
            return self._command_ok(response)
        except (ConnectionError, Dnp3RequestError, ValueError) as exc:
            self.last_error = str(exc)
            return False

    async def operate_analog(self, index: int, value: float, sbo: bool = False) -> bool:
        """按 SBO（先选择后操作）或直接操作方式写模拟量输出。"""
        if sbo and not await self.select_analog(index, value):
            return False
        function = FunctionCode.OPERATE if sbo else FunctionCode.DIRECT_OPERATE
        return await self._analog_operation(function, index, value)

    async def select_analog(self, index: int, value: float) -> bool:
        """选择（SELECT）一个模拟量输出，为后续操作做准备。"""
        return await self._analog_operation(FunctionCode.SELECT, index, value)

    async def operate_analog_configured(self, index: int, value: float, config: dict[str, Any] | None) -> bool:
        """按测点配置执行模拟量输出（支持 SBO 与自定义变体）。"""
        point_config = Dnp3PointConfig.from_mapping(3, config)
        if point_config.control_mode == "sbo" and not await self._analog_operation(
            FunctionCode.SELECT, index, value, point_config.static_variation
        ):
            return False
        function = FunctionCode.OPERATE if point_config.control_mode == "sbo" else FunctionCode.DIRECT_OPERATE
        return await self._analog_operation(function, index, value, point_config.static_variation)

    async def write_binary(self, index: int, value: bool) -> bool:
        """直接操作写二进制输出（无选择过程）。"""
        return await self.operate_binary(index, value, sbo=False)

    @staticmethod
    def _binary_command(value: bool) -> CROB:
        """构造二进制输出的 CROB 锁存命令。"""
        return CROB(control=0x03 if value else 0x04, count=1, on_time_ms=0, off_time_ms=0)

    async def _binary_operation(
        self,
        function: FunctionCode,
        index: int,
        value: bool,
        command: CROB | None = None,
    ) -> bool:
        """执行二进制输出命令（选择/操作/直接操作）并返回状态。"""
        try:
            header = ObjectHeader(12, 1, self._index_qualifier(index), 0, 0, 1)
            command = command or self._binary_command(value)
            response = await self._request(function, [ObjectData(header, [(index, command)])])
            return self._command_ok(response)
        except (ConnectionError, Dnp3RequestError, ValueError) as exc:
            self.last_error = str(exc)
            return False

    async def operate_binary(self, index: int, value: bool, sbo: bool = False) -> bool:
        """按 SBO 或直接操作方式写二进制输出。"""
        if sbo and not await self.select_binary(index, value):
            return False
        return await self.operate_only_binary(index, value) if sbo else await self.write_binary_direct(index, value)

    async def write_binary_direct(self, index: int, value: bool) -> bool:
        """直接操作（DIRECT_OPERATE）写二进制输出。"""
        return await self._binary_operation(FunctionCode.DIRECT_OPERATE, index, value)

    async def select_binary(self, index: int, value: bool) -> bool:
        """选择（SELECT）二进制输出，为后续操作做准备。"""
        return await self._binary_operation(FunctionCode.SELECT, index, value)

    async def operate_only_binary(self, index: int, value: bool) -> bool:
        """操作（OPERATE）已选择的二进制输出。"""
        return await self._binary_operation(FunctionCode.OPERATE, index, value)

    async def operate_binary_configured(self, index: int, value: bool, config: dict[str, Any] | None) -> bool:
        """按测点配置执行二进制输出（支持脉冲与 SBO 模式）。"""
        point_config = Dnp3PointConfig.from_mapping(2, config)
        if point_config.crob_operation == "pulse":
            command = CROB(
                control=0x01 if value else 0x02,
                count=point_config.pulse_count,
                on_time_ms=point_config.pulse_on_ms,
                off_time_ms=point_config.pulse_off_ms,
            )
        else:
            command = self._binary_command(value)
        if point_config.control_mode == "sbo" and not await self._binary_operation(
            FunctionCode.SELECT, index, value, command
        ):
            return False
        function = FunctionCode.OPERATE if point_config.control_mode == "sbo" else FunctionCode.DIRECT_OPERATE
        return await self._binary_operation(function, index, value, command)

    async def sync_time(self) -> bool:
        """用延迟测量结果补偿往返时延后，向对端写入当前时间。"""
        started = time.monotonic()
        delay_ms = await self.measure_delay()
        if delay_ms is None:
            return False
        elapsed_ms = int((time.monotonic() - started) * 1000)
        timestamp = DNP3Timestamp(int(time.time() * 1000) + max(delay_ms, elapsed_ms // 2))
        obj = ObjectData(ObjectHeader(50, 1, Qualifier.COUNT_8, 0, 0, 1), [timestamp])
        try:
            return self._response_success(await self._request(FunctionCode.WRITE, [obj]))
        except (ConnectionError, Dnp3RequestError, ValueError) as exc:
            self.last_error = str(exc)
            return False

    async def measure_delay(self) -> int | None:
        """测量对端精细时延（毫秒，G52V2），供时间同步补偿使用。"""
        try:
            response = await self._request(FunctionCode.DELAY_MEASURE, [])
        except (ConnectionError, Dnp3RequestError, ValueError) as exc:
            self.last_error = str(exc)
            return None
        if not self._response_success(response):
            return None
        return self._delay_from_response(response, variation=2)

    async def cold_restart(self) -> int | None:
        """请求冷重启，返回对端报告的延迟秒数。"""
        return await self._restart(FunctionCode.COLD_RESTART)

    async def warm_restart(self) -> int | None:
        """请求热重启，返回对端报告的延迟秒数。"""
        return await self._restart(FunctionCode.WARM_RESTART)

    async def _restart(self, function: FunctionCode) -> int | None:
        """发送重启请求并解析响应中的延迟秒数。"""
        try:
            response = await self._request(function, [])
        except (ConnectionError, Dnp3RequestError, ValueError) as exc:
            self.last_error = str(exc)
            return None
        if not self._response_success(response):
            return None
        return self._delay_from_response(response, variation=1)

    @staticmethod
    def _delay_from_response(message: AppMessage, variation: int) -> int | None:
        """从 G52 响应对象中提取延迟值。"""
        for obj in message.objects:
            if obj.header.group != 52 or obj.header.variation != variation:
                continue
            for point in obj.points:
                value = point[1] if isinstance(point, tuple) else point
                if isinstance(value, DelayValue):
                    return int(value.value)
        return None

    async def freeze_counters(
        self,
        start: int | None = None,
        stop: int | None = None,
        *,
        clear: bool = False,
        no_ack: bool = False,
    ) -> bool:
        """冻结计数器，支持指定范围、同时清零及无确认模式。"""
        if (start is None) != (stop is None):
            self.last_error = "DNP3计数器冻结范围必须同时提供起止地址"
            return False
        if start is not None and (not 0 <= start <= stop <= 0xFFFF):
            self.last_error = "DNP3计数器冻结范围必须在 0 到 65535 之间"
            return False
        qualifier = (
            Qualifier.ALL_POINTS
            if start is None
            else (Qualifier.RANGE_8_START_STOP if stop <= 0xFF else Qualifier.RANGE_16_START_STOP)
        )
        header = ObjectHeader(20, 0, qualifier, start or 0, stop or 0, 0)
        if clear:
            function = FunctionCode.FREEZE_CLEAR_NO_ACK if no_ack else FunctionCode.FREEZE_CLEAR
        else:
            function = FunctionCode.FREEZE_NO_ACK if no_ack else FunctionCode.FREEZE
        try:
            if no_ack:
                await self._send_no_ack(function, [ObjectData(header)])
                self.last_error = None
                return True
            return self._response_success(await self._request(function, [ObjectData(header)]))
        except (ConnectionError, Dnp3RequestError, ValueError) as exc:
            self.last_error = str(exc)
            return False

    async def _send_no_ack(self, function: FunctionCode, objects: list[ObjectData]) -> None:
        """发送无确认请求（不等待响应）。"""
        if not self._session_ready():
            raise ConnectionError("DNP3 client is not connected")
        async with self._request_lock:
            fragment = build_request(function, self._next_sequence(), objects)
            assert self._transport is not None
            self._transport.send_fragment(fragment, direction=True)
            await asyncio.sleep(0)

    async def enable_unsolicited(self, enabled: bool = True) -> bool:
        """使能或禁止对端的未请求上报（对类1、2、3数据）。"""
        function = FunctionCode.ENABLE_UNSOLICITED if enabled else FunctionCode.DISABLE_UNSOLICITED
        objects = [ObjectData(ObjectHeader(60, variation, Qualifier.ALL_POINTS, 0, 0, 0)) for variation in (2, 3, 4)]
        try:
            return self._response_success(await self._request(function, objects))
        except (ConnectionError, Dnp3RequestError, ValueError) as exc:
            self.last_error = str(exc)
            return False

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取捕获的收发报文列表。"""
        return self._capture.get_messages(limit) if self._capture else []

    def clear_captured_messages(self) -> None:
        """清空捕获的报文。"""
        if self._capture:
            self._capture.clear()
