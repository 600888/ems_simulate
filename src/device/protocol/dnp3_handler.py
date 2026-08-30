"""
DNP3 协议处理器

支持 DNP3 服务端（Outstation）与客户端（Master）两种角色。
接口与 iec104_handler.py / modbus_handler.py 完全一致。

- 服务端：模拟 DNP3 Outstation，响应 Master 轮询与控制
- 客户端：作为 Master 轮询真实 Outstation
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
import time
from typing import Any

from src.config.config import Config
from src.device.core.connection import DisconnectInitiator, DisconnectReason
from src.device.core.message.message_capture import MessageCapture
from src.device.protocol.base_handler import ClientHandler, ServerHandler
from src.enums.points.base_point import BasePoint
from src.enums.points.change_tracker import ChangeSource, track_change
from src.enums.points.yc import Yc
from src.enums.points.yk import Yk
from src.enums.points.yt import Yt
from src.enums.points.yx import Yx


def _index_of(point: BasePoint) -> int:
    """DNP3 以 index 寻址，测点 address 承载 DNP3 索引。"""
    index = int(point.address)
    if not 0 <= index <= 0xFFFF:
        raise ValueError(f"DNP3点索引必须在 0 到 65535 之间: {index}")
    return index


def _decode_value(point: BasePoint, value: Any) -> Any:
    """将 DNP3 原始值转换为测点值。"""
    if value is None:
        return None
    if isinstance(point, (Yx, Yk)):
        return int(bool(value))
    if isinstance(point, (Yc, Yt)):
        return float(value)
    return value


# DNP3 对象组 → 可命中的组集合（静态组 + 事件组）
_READ_GROUPS_MAP: dict[int, tuple[int, ...]] = {
    0: (30, 32),  # 遥测：G30 静态 / G32 事件
    1: (1, 2),  # 遥信：G1 静态 / G2 事件
    2: (10, 12),  # 遥控：G10 静态 / G12 事件
    3: (40, 41),  # 遥调：G40 静态 / G41 事件
}
# 主动读取用的主对象组（静态组）
_READ_PRIMARY_GROUP_MAP: dict[int, int] = {
    0: 30,
    1: 1,
    2: 10,
    3: 40,
}

# DNP3 对象组 → 应用层测点类型。静态响应和事件/主动上报使用同一映射。
_FRAME_TYPE_BY_GROUP: dict[int, int] = {
    30: 0,
    32: 0,
    1: 1,
    2: 1,
    10: 2,
    12: 2,
    40: 3,
    41: 3,
}


def _READ_GROUPS(frame_type: int) -> tuple[int, ...]:
    """返回测点类型对应的可命中对象组集合。"""
    return _READ_GROUPS_MAP.get(frame_type, (30,))


def _READ_PRIMARY_GROUP(frame_type: int) -> int:
    """返回测点类型对应的主动读取主对象组。"""
    return _READ_PRIMARY_GROUP_MAP.get(frame_type, 30)


class DNP3ServerHandler(ServerHandler):
    """DNP3 服务端（Outstation）处理器"""

    def __init__(self, log=None):
        super().__init__()
        self._server = None
        self._log = log
        # index → BasePoint 映射，用于收到 Master 控制后更新应用层测点值
        self._point_map: dict[tuple[int, int], BasePoint] = {}

    def initialize(self, config: dict[str, Any]) -> None:
        """初始化 DNP3 服务器。

        config 包含:
            - ip: 监听 IP（默认 0.0.0.0）
            - port: 监听端口（默认 20000）
            - runtime: DNP3 运行参数（地址、确认、事件缓冲等）
        """
        from src.proto.dnp3.dnp3_server import Dnp3Server

        self._config = config
        self._configure_connection_monitoring(config, supported=True)
        ip = (config.get("ip") or "").strip() or Config.DEFAULT_IP
        port = config.get("port", Config.DNP3_DEFAULT_PORT)
        runtime = config.get("runtime", {})
        security = config.get("security", {})

        from src.proto.dnp3.tls import create_server_ssl_context

        # DNP3 地址：优先 runtime，其次默认
        local_addr = int(runtime.get("local_address", 1))
        master_addr = int(runtime.get("remote_address", 0))

        self._server: Dnp3Server = Dnp3Server(log=self._log)
        self._server.set_addresses(local_addr, master_addr)
        self._server.set_server_ip(ip)
        self._server.set_server_port(port)
        self._server.set_ssl_context(create_server_ssl_context(security))
        self._server.set_parameters(**runtime)
        self._server.set_message_capture(self._new_capture())
        self._server.set_connection_callbacks(
            on_connect=self._on_connection_opened,
            on_activity=self._on_connection_activity,
            on_disconnect=self._on_connection_closed,
        )

    def _on_connection_opened(self, key, remote_endpoint, local_endpoint) -> None:
        """连接建立时记录连接监控信息。"""
        security = self._server.connection_security if self._server else {"tls": False}
        self._open_connection(
            key,
            remote_endpoint=remote_endpoint,
            local_endpoint=local_endpoint,
            security=security,
        )

    def _on_connection_activity(self, key, direction: str, size: int) -> None:
        """连接收发活动时累计收发字节与消息数。"""
        if direction == "rx":
            self._record_connection_activity(key, rx_bytes=size, rx_messages=1)
        else:
            self._record_connection_activity(key, tx_bytes=size, tx_messages=1)

    def _on_connection_closed(self, key, reason_name: str, detail: str | None) -> None:
        """连接断开时映射断开原因与发起方并记录。"""
        reason_map = {
            "remote_closed": (DisconnectReason.REMOTE_CLOSED, DisconnectInitiator.REMOTE),
            "network_reset": (DisconnectReason.NETWORK_RESET, DisconnectInitiator.NETWORK),
            "server_stopped": (DisconnectReason.SERVER_STOPPED, DisconnectInitiator.SERVER),
            "connection_replaced": (DisconnectReason.CONNECTION_REPLACED, DisconnectInitiator.SERVER),
            "protocol_error": (DisconnectReason.PROTOCOL_ERROR, DisconnectInitiator.REMOTE),
        }
        reason, initiator = reason_map.get(
            reason_name,
            (DisconnectReason.UNKNOWN, DisconnectInitiator.UNKNOWN),
        )
        self._close_connection(key, reason=reason, initiator=initiator, detail=detail)

    def _new_capture(self) -> MessageCapture:
        """新建一个报文捕获器。"""
        return MessageCapture()

    def get_value_by_address(self, func_code: int, slave_id: int, address: int) -> Any:
        """按地址读取值（DNP3 以 index 寻址，address 即测点索引，func_code 为 frame_type）。"""
        if self._server:
            return self._server.get_point_value(int(address), frame_type=int(func_code))
        return None

    def set_value_by_address(self, func_code: int, slave_id: int, address: int, value: Any) -> None:
        """按地址设置值（DNP3 以 index 寻址）。"""
        if self._server:
            self._server.set_point_value(int(address), value, frame_type=int(func_code))

    async def start(self) -> bool:
        """启动 DNP3 服务端。"""
        if self._server:
            # 已有 capture 由 initialize 建立，保持复用；仅当基类显式设置了才同步
            if self._message_capture is not None:
                self._server.set_message_capture(self._message_capture)
            ok = await self._server.start()
            self._is_running = ok
            return ok
        return False

    async def stop(self) -> bool:
        """关闭所有连接并停止 DNP3 服务端。"""
        if self._server:
            self._close_all_connections()
            ok = await self._server.stop()
            self._is_running = False
            return ok
        return False

    def read_value(self, point: BasePoint) -> Any:
        """读取指定测点在服务端数据库中的当前值。"""
        if self._server:
            index = _index_of(point)
            value = self._server.get_point_value(index, frame_type=point.frame_type)
            return _decode_value(point, value)
        return None

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """将应用层测点值推送到 Outstation 数据库。"""
        if self._server:
            index = _index_of(point)
            self._server.set_point_value(index, value, frame_type=point.frame_type)
            return True
        return False

    async def read_value_async(self, point: BasePoint) -> Any:
        """异步读取指定测点值（服务端本地读取）。"""
        return self.read_value(point)

    async def write_value_async(self, point: BasePoint, value: Any) -> bool:
        """异步设置指定测点值（服务端本地写入）。"""
        return self.write_value(point, value)

    def add_points(self, points: list[BasePoint]) -> None:
        """添加测点到 DNP3 Outstation 数据库。"""
        if not self._server:
            return

        for point in points:
            index = _index_of(point)
            frame_type = point.frame_type
            point_config = getattr(point, "dnp3_config", None)
            if frame_type == 0:  # 遥测
                self._server.add_analog_input(index, dnp3_config=point_config)
            elif frame_type == 1:  # 遥信
                self._server.add_binary_input(index, dnp3_config=point_config)
            elif frame_type == 2:  # 遥控
                self._server.add_binary_output(index, dnp3_config=point_config)
            elif frame_type == 3:  # 遥调
                self._server.add_analog_output(index, dnp3_config=point_config)
            self._point_map[(frame_type, index)] = point

        self._server.set_on_command_callback(self._on_command_received)

    def _on_command_received(self, index: int, value: Any, frame_type: int = 0) -> None:
        """收到 Master 的遥控/遥调命令，同步更新应用层测点值。"""
        point = self._point_map.get((frame_type, int(index)))
        if point is None:
            if self._log:
                self._log.warning(f"DNP3 收到 index {index} 的控制，未找到对应测点")
            return
        try:
            new_value = _decode_value(point, value)
            point.value = new_value
            if self._log:
                self._log.info(f"DNP3 控制已应用: {point.code} = {new_value}")
        except Exception as e:
            if self._log:
                self._log.error(f"DNP3 应用控制值失败: {e}")

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取服务端捕获的收发报文列表。"""
        if self._server:
            return self._server.get_captured_messages(limit)
        return []

    def clear_captured_messages(self) -> None:
        """清空服务端捕获的报文。"""
        if self._server:
            self._server.clear_captured_messages()

    def get_avg_time(self) -> dict:
        """获取服务端报文捕获的平均处理时间统计。"""
        if self._server and hasattr(self._server, "message_capture"):
            cap = self._server.message_capture if hasattr(self._server, "message_capture") else None
            if cap and hasattr(cap, "get_avg_time"):
                return cap.get_avg_time()
        return {}

    @property
    def server(self):
        """获取底层 DNP3 服务端对象（供 Device.server 使用）"""
        return self._server


class DNP3ClientHandler(ClientHandler):
    """DNP3 客户端（Master）处理器"""

    def __init__(self, log=None):
        super().__init__()
        self._client = None
        self._log = log
        self._event_poll_task: asyncio.Task[None] | None = None
        self._time_sync_task: asyncio.Task[None] | None = None
        self._last_time_sync: dict[str, Any] | None = None
        # (frame_type, index) → BasePoint，用于把协议缓存更新同步到界面数据模型。
        self._point_map: dict[tuple[int, int], BasePoint] = {}

    def initialize(self, config: dict[str, Any]) -> None:
        """初始化 DNP3 客户端配置，创建底层 Dnp3Client 对象。"""
        from src.proto.dnp3.dnp3_client import Dnp3Client

        self._config = config
        ip = (config.get("ip") or "").strip() or "127.0.0.1"
        port = config.get("port", Config.DNP3_DEFAULT_PORT)
        runtime = config.get("runtime", {})
        security = config.get("security", {})

        from src.proto.dnp3.tls import create_client_ssl_context

        local_addr = int(runtime.get("local_address", 0))
        outstation_addr = int(runtime.get("remote_address", 1))

        self._client: Dnp3Client = Dnp3Client(log=self._log)
        self._client.set_addresses(local_addr, outstation_addr)
        self._client.set_server_ip(ip)
        self._client.set_server_port(port)
        self._client.set_ssl_context(create_client_ssl_context(security))
        self._client.set_parameters(**runtime)
        self._client.set_message_capture(self._new_capture())
        self._client.set_connection_callbacks(
            on_connect=self._on_connection_opened,
            on_activity=self._on_connection_activity,
            on_disconnect=self._on_connection_closed,
            on_timeout=self._on_request_timeout,
        )
        self._client.set_on_point_update_callback(self._on_point_update)

    def _on_connection_opened(self, remote_endpoint, local_endpoint) -> None:
        """连接建立后置运行标志，并按需启动时间同步任务。"""
        self._is_running = True
        if self._config.get("runtime", {}).get("time_sync_enabled", False):
            if self._time_sync_task is None or self._time_sync_task.done():
                self._time_sync_task = asyncio.create_task(self._sync_time())
        if self._log:
            self._log.info(f"DNP3连接已建立: remote={remote_endpoint}, local={local_endpoint}")

    def _on_connection_activity(self, direction: str, size: int) -> None:
        """连接收发活动时记录 debug 日志。"""
        if self._log and hasattr(self._log, "debug"):
            self._log.debug(f"DNP3连接活动: direction={direction}, bytes={size}")

    def _on_connection_closed(self, reason: str, detail: str | None) -> None:
        """连接断开时置停止标志并记录警告日志。"""
        self._is_running = False
        if self._log:
            self._log.warning(f"DNP3连接断开: reason={reason}, detail={detail or '-'}")

    def _on_request_timeout(self, pending) -> None:
        """请求超时时记录包含功能码、序号与尝试次数的警告。"""
        if self._log:
            self._log.warning(
                "DNP3请求超时: "
                f"function={pending.function.name}, seq={pending.sequence}, "
                f"attempt={pending.attempt + 1}, objects={pending.objects}"
            )

    def _new_capture(self) -> MessageCapture:
        """新建一个报文捕获器。"""
        return MessageCapture()

    async def connect(self) -> bool:
        """连接到 DNP3 Outstation（异步，覆盖基类抽象）。"""
        if self._client:
            ok = await self._client.start()
            self._is_running = ok
            if ok:
                self._start_event_polling()
            return ok
        return False

    def disconnect(self) -> None:
        """断开连接（同步标记；实际关闭由 async stop 处理）。"""
        self._is_running = False

    async def start(self) -> bool:
        """启动 DNP3 客户端并连接对端，成功后启动事件轮询。"""
        if self._client:
            # 已有 capture 由 initialize 建立，保持复用；仅当基类显式设置了才同步
            if self._message_capture is not None:
                self._client.set_message_capture(self._message_capture)
            ok = await self._client.start()
            self._is_running = ok
            if ok:
                self._start_event_polling()
            return ok
        return False

    async def stop(self) -> bool:
        """停止事件轮询与时间同步任务，并关闭 DNP3 客户端。"""
        await self._stop_event_polling()
        if self._time_sync_task is not None:
            self._time_sync_task.cancel()
            try:
                await self._time_sync_task
            except asyncio.CancelledError:
                pass
            self._time_sync_task = None
        if self._client:
            ok = await self._client.stop()
            self._is_running = False
            return ok
        return False

    def _start_event_polling(self) -> None:
        """按配置启动事件轮询任务（周期小于等于0 则不启动）。"""
        runtime = self._config.get("runtime", {})
        interval = int(runtime.get("event_interval_s", 0))
        if interval <= 0 or self._event_poll_task is not None:
            return
        if bool(runtime.get("enable_unsolicited", False)):
            interval = max(interval, 60)
        self._event_poll_task = asyncio.create_task(self._event_poll_loop(interval))

    async def _stop_event_polling(self) -> None:
        """取消并等待事件轮询任务结束。"""
        if self._event_poll_task is None:
            return
        self._event_poll_task.cancel()
        try:
            await self._event_poll_task
        except asyncio.CancelledError:
            pass
        self._event_poll_task = None

    async def _event_poll_loop(self, interval: int) -> None:
        """按固定周期发送事件轮询请求。"""
        try:
            while True:
                await asyncio.sleep(interval)
                if not self._client or not self._client.is_connected:
                    continue
                if not await self._client.send_event_poll() and self._log:
                    self._log.warning(f"DNP3事件轮询失败: {self._client.last_error}")
        except asyncio.CancelledError:
            return

    async def _sync_time(self) -> None:
        """执行一次时间同步并记录同步结果。"""
        started = time.time()
        ok = bool(self._client and await self._client.sync_time())
        self._last_time_sync = {
            "success": ok,
            "timestamp": started,
            "error": None if ok or not self._client else self._client.last_error,
        }
        if not ok and self._log:
            self._log.warning(f"DNP3时间同步失败: {self._last_time_sync['error']}")

    def read_value(self, point: BasePoint) -> Any:
        """从客户端缓存读取测点值，优先命中主对象组。"""
        if not self._client:
            return None
        index = _index_of(point)
        # DNP3 对象组：遥测 G30/G32、遥信 G1/G2、遥控 G10/G12、遥调 G40/G41
        # 完整性/静态轮询可能返回静态组或事件组，逐个尝试命中缓存。
        groups = _READ_GROUPS(point.frame_type)
        for g in groups:
            value = self._client.read_point(index, g, frame_type=point.frame_type)
            if value is not None:
                return _decode_value(point, value)
        return None

    async def read_metadata_async(self, point: BasePoint) -> dict[str, Any]:
        """读取测点的缓存元数据（品质与时间戳）。"""
        if not self._client:
            return {"quality": {}, "timestamp": {}}
        index = _index_of(point)
        for group in _READ_GROUPS(point.frame_type):
            metadata = self._client.read_point_metadata(index, group)
            if metadata is not None:
                timestamp = metadata.get("timestamp")
                timestamp_ms = int(timestamp.timestamp() * 1000) if hasattr(timestamp, "timestamp") else None
                quality = dict(metadata.get("quality") or {})
                invalid = not metadata.get("valid", False) or quality.get("communication_lost", False)
                quality.update(
                    validity=2 if invalid else 0,
                    detailQuality=f"flags=0x{int(metadata.get('flags') or 0):02X}",
                    source=1 if quality.get("remote_forced") else 0,
                    test=False,
                    operatorBlocked=bool(quality.get("local_forced")),
                )
                return {
                    **metadata,
                    "quality": quality,
                    "timestamp": {
                        "unixTimestampMs": timestamp_ms,
                        "seconds": timestamp_ms / 1000 if timestamp_ms is not None else None,
                        "timeAccuracy": None,
                        "leapSecondsKnown": None,
                        "clockFailure": False,
                        "clockNotSynchronized": False,
                        "iso": timestamp.isoformat() if hasattr(timestamp, "isoformat") else None,
                    },
                }
        return {"quality": {}, "timestamp": {}}

    async def active_read_value_async(self, point: BasePoint) -> Any:
        """DNP3 主动读取单个测点：触发完整性轮询刷新缓存，等待响应后返回该 index 最新值。

        与 read_value/read_value_async（读本地缓存）不同，此方法会真正发送网络请求
        获取 Outstation 最新数据，再取指定测点的值。
        """
        if not self._client:
            return None
        index = _index_of(point)
        group = _READ_PRIMARY_GROUP(point.frame_type)
        result = await self._client.read_point_active(index, group)
        return _decode_value(point, result)

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """同步写入口：DNP3 客户端写需要网络 await，此同步版仅允许本地（无操作）使用。

        界面写入走 write_value_async（异步发网络请求）。
        """
        return False

    async def read_value_async(self, point: BasePoint) -> Any:
        """异步读取（主动读）：发网络请求获取最新值并返回。"""
        return await self.active_read_value_async(point)

    async def read_points_batch_async(self, points: Sequence[BasePoint]) -> dict[str, Any]:
        """用一次 Class 0 完整性轮询刷新并返回多个测点。

        完整性轮询会同时返回 Outstation 的全部静态点，因此批量读取不能复用
        ``read_value_async`` 逐点发送轮询，否则界面配置的轮询间隔会被每点固定
        等待时间掩盖。
        """
        if not self._client or not points:
            return {}
        requests = [(_index_of(point), _READ_PRIMARY_GROUP(point.frame_type)) for point in points]
        raw_values = await self._client.read_points_active(requests)
        return {
            point.code: _decode_value(
                point,
                raw_values.get((_index_of(point), _READ_PRIMARY_GROUP(point.frame_type))),
            )
            for point in points
        }

    async def write_value_async(self, point: BasePoint, value: Any) -> bool:
        """异步写入：向对端 Outstation 下发遥控/遥调（Direct Operate）。"""
        if not self._client:
            return False
        index = _index_of(point)
        try:
            if point.frame_type == 2:  # 遥控
                return await self._client.operate_binary_configured(
                    index, bool(value), getattr(point, "dnp3_config", None)
                )
            if point.frame_type == 3:  # 遥调
                return await self._client.operate_analog_configured(
                    index, float(value), getattr(point, "dnp3_config", None)
                )
            if point.frame_type == 1:  # 遥信（通常只读）
                return await self._client.write_binary(index, bool(value))
            return await self._client.write_analog(index, float(value))
        except (ConnectionError, TimeoutError, ValueError, RuntimeError) as exc:
            if self._log:
                self._log.error(f"DNP3写入失败: index={index}, frame_type={point.frame_type}, error={exc}")
            return False

    def add_points(self, points: list[BasePoint]) -> None:
        """注册 Master 测点映射，使轮询和主动上报能更新应用层测点。"""
        for point in points:
            self._point_map[(int(point.frame_type), _index_of(point))] = point

    def _on_point_update(self, group: int, index: int, value: Any, source: str) -> None:
        """把底层 Master 缓存更新同步到设备测点，供表格自动刷新读取。"""
        frame_type = _FRAME_TYPE_BY_GROUP.get(int(group))
        if frame_type is None:
            return
        point = self._point_map.get((frame_type, int(index)))
        if point is None:
            if self._log and hasattr(self._log, "debug"):
                self._log.debug(f"DNP3收到未配置测点: group={group}, index={index}, source={source}")
            return

        new_value = _decode_value(point, value)
        detail = "DNP3主动上报" if source == "unsolicited" else "DNP3响应更新"
        with track_change(ChangeSource.CLIENT_READ, f"{detail} {point.code}"):
            point.value = new_value
        point.is_valid = True

    async def send_integrity_poll(self) -> bool:
        """发送 Class 0 完整性轮询并返回是否成功。"""
        if self._client:
            return await self._client.send_integrity_poll()
        return False

    async def send_event_poll(self) -> bool:
        """发送事件轮询并返回是否成功。"""
        if self._client:
            return await self._client.send_event_poll()
        return False

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取客户端捕获的收发报文列表。"""
        if self._client:
            return self._client.get_captured_messages(limit)
        return []

    def clear_captured_messages(self) -> None:
        """清空客户端捕获的报文。"""
        if self._client:
            self._client.clear_captured_messages()

    def get_avg_time(self) -> dict:
        """获取客户端报文捕获的平均处理时间统计。"""
        if self._client and hasattr(self._client, "message_capture"):
            cap = self._client.message_capture if hasattr(self._client, "message_capture") else None
            if cap and hasattr(cap, "get_avg_time"):
                return cap.get_avg_time()
        return {}

    @property
    def client(self):
        """获取底层 DNP3 客户端对象（供 Device.client 使用）"""
        return self._client

    @property
    def last_error(self) -> str | None:
        """获取客户端最后一条错误信息。"""
        return self._client.last_error if self._client else None

    @property
    def last_time_sync(self) -> dict[str, Any] | None:
        """获取最近一次时间同步的结果记录。"""
        return self._last_time_sync
