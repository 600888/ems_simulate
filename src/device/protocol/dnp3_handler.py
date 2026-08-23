"""
DNP3 协议处理器

支持 DNP3 服务端（Outstation）与客户端（Master）两种角色。
接口与 iec104_handler.py / modbus_handler.py 完全一致。

- 服务端：模拟 DNP3 Outstation，响应 Master 轮询与控制
- 客户端：作为 Master 轮询真实 Outstation
"""

from __future__ import annotations

from typing import Any

from src.config.config import Config
from src.device.core.connection import DisconnectInitiator, DisconnectReason
from src.device.core.message.message_capture import MessageCapture
from src.device.protocol.base_handler import ClientHandler, ServerHandler
from src.enums.points.base_point import BasePoint
from src.enums.points.yc import Yc
from src.enums.points.yk import Yk
from src.enums.points.yt import Yt
from src.enums.points.yx import Yx


def _index_of(point: BasePoint) -> int:
    """DNP3 以 index 寻址，测点 address 承载 DNP3 索引。"""
    return int(point.address)


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


def _READ_GROUPS(frame_type: int) -> tuple[int, ...]:
    return _READ_GROUPS_MAP.get(frame_type, (30,))


def _READ_PRIMARY_GROUP(frame_type: int) -> int:
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

        # DNP3 地址：优先 runtime，其次默认
        local_addr = int(runtime.get("local_address", 1))
        master_addr = int(runtime.get("remote_address", 0))

        self._server: Dnp3Server = Dnp3Server(log=self._log)
        self._server.set_addresses(local_addr, master_addr)
        self._server.set_server_ip(ip)
        self._server.set_server_port(port)
        self._server.set_parameters(**runtime)
        self._server.set_message_capture(self._new_capture())
        self._server.set_connection_callbacks(
            on_connect=self._on_connection_opened,
            on_activity=self._on_connection_activity,
            on_disconnect=self._on_connection_closed,
        )

    def _on_connection_opened(self, key, remote_endpoint, local_endpoint) -> None:
        self._open_connection(key, remote_endpoint=remote_endpoint, local_endpoint=local_endpoint)

    def _on_connection_activity(self, key, direction: str, size: int) -> None:
        if direction == "rx":
            self._record_connection_activity(key, rx_bytes=size, rx_messages=1)
        else:
            self._record_connection_activity(key, tx_bytes=size, tx_messages=1)

    def _on_connection_closed(self, key, reason_name: str, detail: str | None) -> None:
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
        if self._server:
            # 已有 capture 由 initialize 建立，保持复用；仅当基类显式设置了才同步
            if self._message_capture is not None:
                self._server.set_message_capture(self._message_capture)
            ok = await self._server.start()
            self._is_running = ok
            return ok
        return False

    async def stop(self) -> bool:
        if self._server:
            self._close_all_connections()
            ok = await self._server.stop()
            self._is_running = False
            return ok
        return False

    def read_value(self, point: BasePoint) -> Any:
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
        return self.read_value(point)

    async def write_value_async(self, point: BasePoint, value: Any) -> bool:
        return self.write_value(point, value)

    def add_points(self, points: list[BasePoint]) -> None:
        """添加测点到 DNP3 Outstation 数据库。"""
        if not self._server:
            return

        for point in points:
            index = _index_of(point)
            frame_type = point.frame_type
            if frame_type == 0:  # 遥测
                self._server.add_analog_input(index)
            elif frame_type == 1:  # 遥信
                self._server.add_binary_input(index)
            elif frame_type == 2:  # 遥控
                self._server.add_binary_output(index)
            elif frame_type == 3:  # 遥调
                self._server.add_analog_output(index)
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
        if self._server:
            return self._server.get_captured_messages(limit)
        return []

    def clear_captured_messages(self) -> None:
        if self._server:
            self._server.clear_captured_messages()

    def get_avg_time(self) -> dict:
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

    def initialize(self, config: dict[str, Any]) -> None:
        from src.proto.dnp3.dnp3_client import Dnp3Client

        self._config = config
        ip = (config.get("ip") or "").strip() or "127.0.0.1"
        port = config.get("port", Config.DNP3_DEFAULT_PORT)
        runtime = config.get("runtime", {})

        local_addr = int(runtime.get("local_address", 0))
        outstation_addr = int(runtime.get("remote_address", 1))

        self._client: Dnp3Client = Dnp3Client(log=self._log)
        self._client.set_addresses(local_addr, outstation_addr)
        self._client.set_server_ip(ip)
        self._client.set_server_port(port)
        self._client.set_parameters(**runtime)
        self._client.set_message_capture(self._new_capture())

    def _new_capture(self) -> MessageCapture:
        return MessageCapture()

    async def connect(self) -> bool:
        """连接到 DNP3 Outstation（异步，覆盖基类抽象）。"""
        if self._client:
            ok = await self._client.start()
            self._is_running = ok
            return ok
        return False

    def disconnect(self) -> None:
        """断开连接（同步标记；实际关闭由 async stop 处理）。"""
        self._is_running = False

    async def start(self) -> bool:
        if self._client:
            # 已有 capture 由 initialize 建立，保持复用；仅当基类显式设置了才同步
            if self._message_capture is not None:
                self._client.set_message_capture(self._message_capture)
            ok = await self._client.start()
            self._is_running = ok
            return ok
        return False

    async def stop(self) -> bool:
        if self._client:
            ok = await self._client.stop()
            self._is_running = False
            return ok
        return False

    def read_value(self, point: BasePoint) -> Any:
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

    async def write_value_async(self, point: BasePoint, value: Any) -> bool:
        """异步写入：向对端 Outstation 下发遥控/遥调（Direct Operate）。"""
        if not self._client:
            return False
        index = _index_of(point)
        try:
            if point.frame_type == 2:  # 遥控
                return await self._client.operate_binary(index, bool(value), sbo=False)
            if point.frame_type == 3:  # 遥调
                return await self._client.write_analog(index, float(value))
            if point.frame_type == 1:  # 遥信（通常只读）
                return await self._client.write_binary(index, bool(value))
            return await self._client.write_analog(index, float(value))
        except Exception:
            return False

    def add_points(self, points: list[BasePoint]) -> None:
        """Master 模式无出站点注册，忽略。"""
        pass

    async def send_integrity_poll(self) -> bool:
        if self._client:
            return await self._client.send_integrity_poll()
        return False

    async def send_event_poll(self) -> bool:
        if self._client:
            return await self._client.send_event_poll()
        return False

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        if self._client:
            return self._client.get_captured_messages(limit)
        return []

    def clear_captured_messages(self) -> None:
        if self._client:
            self._client.clear_captured_messages()

    def get_avg_time(self) -> dict:
        if self._client and hasattr(self._client, "message_capture"):
            cap = self._client.message_capture if hasattr(self._client, "message_capture") else None
            if cap and hasattr(cap, "get_avg_time"):
                return cap.get_avg_time()
        return {}

    @property
    def client(self):
        """获取底层 DNP3 客户端对象（供 Device.client 使用）"""
        return self._client
