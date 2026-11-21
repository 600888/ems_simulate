"""
IEC104 协议处理器
支持 IEC104 服务端和客户端
支持多 Station（多从站/多公共地址）
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import time
from typing import Any

import c104

from src.config.config import Config
from src.device.core.connection import ConnectionState, DisconnectInitiator, DisconnectReason
from src.device.protocol.base_handler import ClientHandler, ServerHandler
from src.device.protocol.iec60870_common import decode_point_value, resolve_asdu_type
from src.enums.point_data import Yc, Yk, Yt, Yx
from src.enums.points.base_point import BasePoint
from src.enums.points.iec104_command_mode import IEC104CommandMode
from src.enums.points.iec104_quality import (
    encode_quality_for_c104,
    supports_quality,
)
from src.enums.points.iec104_type import IEC104_TYPE_REGISTRY, IEC104ValueType, encode_iec104_value


def _resolve_c104_type(point: BasePoint) -> c104.Type:
    """根据测点的 iec_type_id 解析 c104.Type 常量

    Args:
        point: 测点对象

    Returns:
        c104.Type 枚举值
    """
    iec_type = resolve_asdu_type(point)
    # c104 库使用 TypeID 字符串作为属性名映射到 c104.Type
    return getattr(c104.Type, iec_type.value)


_decode_c104_point_value = decode_point_value


def _resolve_command_mode(point: BasePoint) -> c104.CommandMode:
    mode = IEC104CommandMode(getattr(point, "iec_command_mode", IEC104CommandMode.DIRECT))
    return getattr(c104.CommandMode, mode.value)


def _update_command_mode(stations: dict, point: BasePoint, mode: str) -> None:
    """Apply a saved workflow without transmitting a control command."""
    common_address = int(point.rtu_addr) if point.rtu_addr else 1
    station = stations.get(common_address)
    if station is not None:
        command = station.get_point(io_address=int(point.address))
        if command is not None:
            command.command_mode = getattr(c104.CommandMode, IEC104CommandMode(mode).value)


def _native_value(point: BasePoint, value: Any) -> Any:
    asdu_type = resolve_asdu_type(point)
    kind = IEC104_TYPE_REGISTRY[asdu_type].value_type
    if kind is IEC104ValueType.DOUBLE:
        return c104.Double(int(value))
    if kind is IEC104ValueType.STEP:
        return c104.Step(int(value))
    if kind is IEC104ValueType.SINGLE:
        return bool(value)
    return encode_iec104_value(value, asdu_type)


def _point_location(point: BasePoint) -> tuple[int, int]:
    return int(point.rtu_addr or 1), int(point.address)


def _refresh_native_point(handler, transport, point: BasePoint, previous: BasePoint, *, server: bool) -> None:
    """Replace only the IEC104 registration whose address or ASDU type changed."""
    old_key, new_key = _point_location(previous), _point_location(point)
    if old_key == new_key and resolve_asdu_type(previous) == resolve_asdu_type(point):
        if point.frame_type in (2, 3) and point.iec_command_mode != previous.iec_command_mode:
            handler.update_command_mode(point, point.iec_command_mode)
        if server:
            station = transport.stations.get(new_key[0])
            native = station.get_point(io_address=new_key[1]) if station else None
            if native is not None and point.value != previous.value:
                native.value = _native_value(point, point.value)
            if (
                native is not None
                and native.quality is not None
                and point.iec_quality_value != previous.iec_quality_value
            ):
                native.quality = c104.Quality(value=encode_quality_for_c104(point.iec_quality, point.frame_type))
        return

    old_station = transport.stations.get(old_key[0])
    old_native = old_station.get_point(io_address=old_key[1]) if old_station else None
    new_station = transport.stations.get(new_key[0])
    if old_key != new_key and new_station and new_station.get_point(io_address=new_key[1]) is not None:
        raise ValueError("目标公共地址和信息对象地址已注册")

    def remove(key, native):
        if not transport.stations[key[0]].remove_point(io_address=key[1]):
            raise ValueError("无法注销原 IEC104 测点")
        collection = transport.commands if server and point.frame_type in (2, 3) else transport.points
        if native in collection:
            collection.remove(native)
        if server:
            handler._command_point_map.pop(key, None)

    def register(definition):
        handler.add_points([definition])
        native = transport.stations[definition.rtu_addr or 1].get_point(io_address=int(definition.address))
        if native is None or native.type != _resolve_c104_type(definition):
            raise ValueError("无法注册新的 IEC104 测点")
        return native

    old_info = old_native.info if old_native is not None else None
    old_type = old_native.type if old_native is not None else None
    if old_key == new_key and old_native is not None:
        remove(old_key, old_native)
    replacement = None
    try:
        replacement = register(point)
        if old_info is not None and old_type == replacement.type:
            replacement.info = old_info
        if server and (old_info is None or old_type != replacement.type or point.value != previous.value):
            replacement.value = _native_value(point, point.value)
        if server and replacement.quality is not None:
            replacement.quality = c104.Quality(value=encode_quality_for_c104(point.iec_quality, point.frame_type))
        if old_key != new_key and old_native is not None:
            remove(old_key, old_native)
    except Exception:
        if replacement is not None:
            remove(new_key, replacement)
        if old_key == new_key and old_native is not None:
            register(previous).info = old_info
            if server and previous.frame_type in (2, 3):
                handler._command_point_map[old_key] = point
        raise


def _c104_connection_time_utc(value: datetime | None) -> datetime | None:
    """Normalize c104's native local datetime before registry storage.

    The chrono binding returns local wall time without tzinfo. astimezone
    interprets that in the host timezone and also handles aware values.
    """
    return value.astimezone(UTC) if value is not None else None


class IEC104ServerHandler(ServerHandler):
    """IEC104 服务端处理器"""

    def __init__(self, log=None):
        super().__init__()
        self._server = None
        self._log = log
        # 命令点 (common_address, IOA) → BasePoint 映射，用于收到客户端命令后更新应用层点值
        self._command_point_map: dict[tuple[int, int], BasePoint] = {}
        # 连接级实时流量：key -> (rx_bytes, tx_bytes, rx_frames, tx_frames) 上次快照
        self._traffic_snapshot: dict[str, tuple[int, int, int, int]] = {}
        self._traffic_task = None

    def initialize(self, config: dict[str, Any]) -> None:
        """初始化 IEC104 服务器

        Args:
            config: 配置字典，包含:
                - ip: 监听 IP（默认 0.0.0.0）
                - port: 监听端口（默认 2404）
                - slave_id_list: 从机 ID 列表，每个从机映射为一个独立的 Station
        """
        from src.proto.iec104.iec104server import IEC104Server

        self._config = config
        ip = config.get("ip", Config.DEFAULT_IP)
        port = config.get("port", Config.IEC104_DEFAULT_PORT)
        runtime = config.get("runtime", {})
        security = config.get("security", {})

        from src.proto.iec104.tls import build_transport_security, load_one_way_tls_config

        self._server: IEC104Server = IEC104Server(
            ip=ip,
            port=port,
            connection_timeout=runtime.get("t0_timeout_s", 10),
            message_timeout=runtime.get("t1_timeout_s", 15),
            confirm_interval=runtime.get("t2_timeout_s", 10),
            keep_alive_interval=runtime.get("t3_interval_s", 20),
            send_window_size=runtime.get("send_window_size", 12),
            receive_window_size=runtime.get("receive_window_size", 8),
            max_connections=runtime.get("max_connections", 0),
            transport_security=build_transport_security(security),
            one_way_tls_config=load_one_way_tls_config(security, client=False),
            connection_history_size=100,
        )
        self._server.set_connection_state_callback(self._on_connection_state_change)

        # 连接监控是否可用，取决于当前 c104 是否编译了连接监控回调。
        # 某些平台（如 ARM）的 c104 裁剪版没有这些回调：此时监控关闭，
        # 但 IEC104 设备本身（Station/测点/读写）仍正常工作。
        self._configure_connection_monitoring(
            config,
            supported=self._server.connection_monitoring_supported,
        )

        # 预创建所有从站对应的 Station（common_address = slave_id）
        slave_id_list = config.get("slave_id_list", [])
        for slave_id in slave_id_list:
            self._server.get_station(common_address=int(slave_id))

    async def start(self) -> bool:
        """启动 IEC104 服务器"""
        try:
            if self._server:
                self._server.start()
                self._is_running = True
                if self._connection_monitoring_supported:
                    self._start_traffic_poller()
                return True
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"启动 IEC104 服务器失败: {e}")
            return False

    async def stop(self) -> bool:
        """停止 IEC104 服务器"""
        try:
            if self._server and hasattr(self._server, "stop"):
                self._stop_traffic_poller()
                self._close_all_connections()
                self._server.stop()
                self._is_running = False
                return True
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"停止 IEC104 服务器失败: {e}")
            return False

    def _start_traffic_poller(self) -> None:
        self._stop_traffic_poller()
        self._traffic_task = asyncio.ensure_future(self._poll_connection_traffic())

    def _stop_traffic_poller(self) -> None:
        if self._traffic_task is not None:
            self._traffic_task.cancel()
            self._traffic_task = None

    async def _poll_connection_traffic(self) -> None:
        """Periodically read each connection's live byte counters and record deltas.

        c104's ``ServerConnection`` exposes per-connection ``bytes_received`` /
        ``bytes_sent`` / ``frames_received`` / ``frames_sent`` counters that update
        live while the session is open, so we snapshot them and feed the deltas to
        the shared registry (which only accepts additive amounts).
        """
        try:
            while self._is_running and self._server is not None:
                await asyncio.sleep(2)
                try:
                    connections = list(getattr(self._server.server, "connections", None) or [])
                except Exception:
                    connections = []
                for con in connections:
                    key = f"iec104:{getattr(con, 'id', None)}"
                    if key not in self._connection_sessions:
                        continue
                    try:
                        rx = int(getattr(con, "bytes_received", 0) or 0)
                        tx = int(getattr(con, "bytes_sent", 0) or 0)
                        frx = int(getattr(con, "frames_received", 0) or 0)
                        ftx = int(getattr(con, "frames_sent", 0) or 0)
                    except Exception:
                        continue
                    last = self._traffic_snapshot.get(key)
                    if last is None:
                        self._traffic_snapshot[key] = (rx, tx, frx, ftx)
                        continue
                    if (rx, tx, frx, ftx) == last:
                        continue
                    self._traffic_snapshot[key] = (rx, tx, frx, ftx)
                    lrx, ltx, lfrx, lftx = last
                    self._record_connection_activity(
                        key,
                        rx_bytes=max(0, rx - lrx),
                        tx_bytes=max(0, tx - ltx),
                        rx_messages=max(0, frx - lfrx),
                        tx_messages=max(0, ftx - lftx),
                    )
        except asyncio.CancelledError:
            pass

    def _on_connection_state_change(
        self,
        server: c104.Server,
        connection: c104.ServerConnection,
        state: c104.ServerConnectionState,
    ) -> None:
        """Translate the fork's exact per-connection lifecycle into the shared registry."""
        key = f"iec104:{connection.id}"
        if state == c104.ServerConnectionState.ESTABLISHED:
            security = {
                "tls": bool(connection.is_secure),
                "version": connection.tls_version,
                "cipher": connection.cipher_suite,
                "client_certificate_sha256": connection.client_certificate_sha256,
                "observed_remote_ip": connection.observed_remote_ip,
                "observed_remote_port": connection.observed_remote_port,
                "correlation_id": connection.correlation_id,
            }
            self._open_connection(
                key,
                remote_endpoint=(connection.remote_ip, connection.remote_port),
                local_endpoint=(connection.local_ip, connection.local_port),
                security={name: value for name, value in security.items() if value not in (None, "")},
                connected_at=_c104_connection_time_utc(connection.connected_at),
            )
            return
        if state == c104.ServerConnectionState.ACTIVE:
            self._update_connection(key, state=ConnectionState.ACTIVE)
            return
        if state == c104.ServerConnectionState.INACTIVE:
            self._update_connection(key, state=ConnectionState.IDLE)
            return
        if state not in (c104.ServerConnectionState.CLOSED, c104.ServerConnectionState.FAILED):
            return

        reason_map = {
            "REMOTE_OR_IO_ERROR": (DisconnectReason.REMOTE_CLOSED, DisconnectInitiator.REMOTE),
            "LOCAL_REQUEST": (DisconnectReason.SERVER_STOPPED, DisconnectInitiator.SERVER),
            "SERVER_STOPPED": (DisconnectReason.SERVER_STOPPED, DisconnectInitiator.SERVER),
            "PROTOCOL_ERROR": (DisconnectReason.PROTOCOL_ERROR, DisconnectInitiator.REMOTE),
            "T1_TIMEOUT": (DisconnectReason.IDLE_TIMEOUT, DisconnectInitiator.SERVER),
            "T3_TIMEOUT": (DisconnectReason.IDLE_TIMEOUT, DisconnectInitiator.SERVER),
            "SECURITY_ERROR": (DisconnectReason.AUTHENTICATION_FAILED, DisconnectInitiator.SERVER),
            "TLS_HANDSHAKE_FAILED": (DisconnectReason.TLS_HANDSHAKE_FAILED, DisconnectInitiator.SERVER),
        }
        reason, initiator = reason_map.get(
            connection.close_reason.name,
            (DisconnectReason.UNKNOWN, DisconnectInitiator.UNKNOWN),
        )
        self._close_connection(
            key,
            reason=reason,
            initiator=initiator,
            detail=connection.error_message,
            disconnected_at=_c104_connection_time_utc(connection.disconnected_at),
            final_stats={
                "rx_bytes": connection.bytes_received,
                "tx_bytes": connection.bytes_sent,
                "rx_messages": connection.frames_received,
                "tx_messages": connection.frames_sent,
                "error_count": int(connection.error_code != 0),
            },
        )

    def read_value(self, point: BasePoint) -> Any:
        """读取测点值"""
        if self._server:
            common_address = int(point.rtu_addr) if point.rtu_addr else 1
            value = self._server.get_point_value(
                io_address=int(point.address),
                frame_type=point.frame_type,
                common_address=common_address,
            )
            if value is not None:
                return _decode_c104_point_value(point, value)
            return None
        return 0

    def reset_point_value(self, point: BasePoint) -> bool:
        """用 ASDU 对应的原生类型清零，不改动测点品质。"""
        if not self._server:
            return False
        station = self._server.stations.get(int(point.rtu_addr or 1))
        native_point = station.get_point(io_address=int(point.address)) if station is not None else None
        if native_point is None:
            return False

        native_point.value = _native_value(point, 0)
        return True

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """用当前 ASDU 类型编码测点值和品质。"""
        if not self._server:
            return False
        common_address, io_address = _point_location(point)
        self._server.set_point_value(
            io_address=io_address,
            value=_native_value(point, value),
            frame_type=point.frame_type,
            common_address=common_address,
        )
        if supports_quality(point.frame_type) and resolve_asdu_type(point) != "M_ME_ND_1":
            self._server.set_point_quality(
                io_address=io_address,
                quality=encode_quality_for_c104(point.iec_quality, point.frame_type),
                frame_type=point.frame_type,
                common_address=common_address,
            )
        return True

    async def read_value_async(self, point: BasePoint) -> Any:
        """异步读取测点值"""
        return self.read_value(point)

    async def write_value_async(self, point: BasePoint, value: Any) -> bool:
        """异步写入测点值"""
        return self.write_value(point, value)

    def add_points(self, points: list[BasePoint]) -> None:
        """添加测点到 IEC104 服务器

        根据每个测点的 rtu_addr（从机地址）将测点路由到对应的 Station。
        """
        if not self._server:
            return

        for point in points:
            frame_type = point.frame_type
            point_type = _resolve_c104_type(point)
            common_address = int(point.rtu_addr) if point.rtu_addr else 1

            if frame_type in (0, 1):  # 遥测/遥信 → 监控点
                self._server.add_monitoring_point(
                    io_address=point.address,
                    point_type=point_type,
                    report_ms=1000,  # 自动上报间隔 1 秒
                    common_address=common_address,
                )
            elif frame_type in (2, 3):  # 遥控/遥调 → 命令点
                cmd_point = self._server.add_command_point(
                    io_address=point.address,
                    point_type=point_type,
                    common_address=common_address,
                    command_mode=_resolve_command_mode(point),
                )
                if cmd_point is None:
                    if self._log:
                        self._log.warning(
                            f"添加命令点失败: code={point.code}, address={point.address}, "
                            f"type={point_type}, common_address={common_address}"
                        )
                    continue
                # 建立 (common_address, IOA) → BasePoint 映射，用于命令接收后同步更新应用层值
                self._command_point_map[(common_address, int(point.address))] = point

        # 注册命令接收回调（每次 add_points 时更新）
        self._server.set_on_command_callback(self._on_command_received)

    def update_command_mode(self, point: BasePoint, mode: str) -> None:
        if self._server:
            _update_command_mode(self._server.stations, point, mode)

    def update_point_definition(self, point: BasePoint, previous: BasePoint) -> None:
        if self._server:
            _refresh_native_point(self, self._server, point, previous, server=True)

    def _on_command_received(self, io_address: int, value, point_type, common_address: int = 1) -> None:
        """
        当服务端收到客户端发送的遥控/遥调命令时，同步更新应用层测点值。

        Args:
            io_address: 信息对象地址(IOA)
            value: 接收到的命令值（c104 原生类型）
            point_type: c104 点类型
            common_address: 站地址（对应从站 slave_id）
        """
        point = self._command_point_map.get((common_address, io_address))
        if point is None:
            if self._log:
                self._log.warning(f"收到站 {common_address} IOA {io_address} 的命令，但未找到对应的应用层测点")
            return

        try:
            new_value = _decode_c104_point_value(point, value)
            point.value = new_value
            if self._log:
                self._log.info(
                    f"服务端收到命令并更新测点 {point.code}(站={common_address}, IOA={io_address}): "
                    f"raw={new_value}, real={getattr(point, 'real_value', new_value)}"
                )
        except Exception as e:
            if self._log:
                self._log.error(f"更新命令接收后的测点值失败: {e}")

    def get_value_by_address(self, func_code: int, slave_id: int, address: int) -> Any:
        """根据地址获取值"""
        if self._server:
            return self._server.get_point_value(io_address=address, frame_type=0, common_address=slave_id)
        return 0

    def set_value_by_address(self, func_code: int, slave_id: int, address: int, value: Any) -> None:
        """根据地址设置值"""
        if self._server:
            self._server.set_point_value(io_address=address, value=value, frame_type=0, common_address=slave_id)

    @property
    def server(self):
        """获取底层服务器对象"""
        return self._server

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取捕获的报文列表"""
        if self._server and hasattr(self._server, "get_captured_messages"):
            return self._server.get_captured_messages(limit)
        return []

    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        if self._server and hasattr(self._server, "clear_captured_messages"):
            self._server.clear_captured_messages()

    def get_avg_time(self) -> dict:
        """获取平均收发时间"""
        if self._server and hasattr(self._server, "message_capture"):
            return self._server.message_capture.get_avg_time()
        return {}


class IEC104ClientHandler(ClientHandler):
    """IEC104 客户端处理器"""

    def __init__(self, log=None):
        super().__init__()
        self._client = None
        self._log = log
        self._connect_timeout = 10.0
        self._reconnect_initial_interval = 2.0
        self._max_reconnect_interval = 30.0
        self._max_reconnect_attempts = 0
        self._reconnect_count = 0
        self._last_reconnect_attempt = 0.0
        self._loop = None
        self._clock_sync_interval = 0
        self._general_interrogation_interval = 0
        self._counter_interrogation_interval = 0
        self._counter_interrogation_on_connect = False
        self._maintenance_task = None
        self._reconnect_lock = asyncio.Lock()

    def initialize(self, config: dict[str, Any]) -> None:
        """初始化 IEC104 客户端

        Args:
            config: 配置字典，包含:
                - ip: 服务器 IP
                - port: 服务器端口（默认 2404）
                - slave_id_list: 从机 ID 列表，每个从机映射为一个独立的 Station
        """
        from src.proto.iec104.iec104client import IEC104Client

        self._config = config
        ip = config.get("ip", "127.0.0.1")
        port = config.get("port", Config.IEC104_DEFAULT_PORT)
        runtime = config.get("runtime", {})
        security = config.get("security", {})
        self._connect_timeout = runtime.get("t0_timeout_s", 10)
        self._reconnect_initial_interval = runtime.get("reconnect_initial_interval_ms", 2000) / 1000
        self._max_reconnect_interval = runtime.get("reconnect_max_interval_ms", 30000) / 1000
        self._max_reconnect_attempts = runtime.get("reconnect_max_attempts", 0)
        self._clock_sync_interval = runtime.get("clock_sync_interval_s", 0)
        self._general_interrogation_interval = runtime.get("general_interrogation_interval_s", 0)
        self._counter_interrogation_interval = runtime.get("counter_interrogation_interval_s", 0)
        self._counter_interrogation_on_connect = runtime.get("counter_interrogation_on_connect", False)

        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

        from src.proto.iec104.tls import build_transport_security, load_one_way_tls_config

        self._client = IEC104Client(
            ip=ip,
            port=port,
            originator_address=runtime.get("originator_address", 0),
            connection_timeout=runtime.get("t0_timeout_s", 10),
            message_timeout=runtime.get("t1_timeout_s", 15),
            confirm_interval=runtime.get("t2_timeout_s", 10),
            keep_alive_interval=runtime.get("t3_interval_s", 20),
            send_window_size=runtime.get("send_window_size", 12),
            receive_window_size=runtime.get("receive_window_size", 8),
            general_interrogation_on_connect=runtime.get("general_interrogation_on_connect", True),
            transport_security=build_transport_security(security),
            one_way_tls_config=load_one_way_tls_config(security, client=True),
        )

        # 预创建所有从站对应的 Station（common_address = slave_id）
        slave_id_list = config.get("slave_id_list", [])
        for slave_id in slave_id_list:
            self._client.get_station(common_address=int(slave_id))

    async def start(self) -> bool:
        """启动客户端（连接服务器）"""
        self._loop = asyncio.get_running_loop()
        connected = await self.connect()
        if connected:
            self._start_maintenance_task()
        return connected

    async def stop(self) -> bool:
        """停止客户端（断开连接）"""
        await self._stop_maintenance_task()
        await asyncio.to_thread(self.disconnect)
        return True

    def _start_maintenance_task(self) -> None:
        if self._maintenance_task and not self._maintenance_task.done():
            return
        self._maintenance_task = asyncio.create_task(self._maintenance_loop())

    async def _stop_maintenance_task(self) -> None:
        if not self._maintenance_task:
            return
        self._maintenance_task.cancel()
        try:
            await self._maintenance_task
        except asyncio.CancelledError:
            pass
        self._maintenance_task = None

    async def _maintenance_loop(self) -> None:
        """持续监控连接，并按配置周期发送链路维护命令。"""
        now = time.monotonic()
        next_clock_sync = now + self._clock_sync_interval if self._clock_sync_interval > 0 else None
        next_interrogation = (
            now + self._general_interrogation_interval if self._general_interrogation_interval > 0 else None
        )
        next_counter_interrogation = (
            now + self._counter_interrogation_interval if self._counter_interrogation_interval > 0 else None
        )

        while True:
            await asyncio.sleep(1)
            if not self.is_running and not await self._try_reconnect():
                continue

            now = time.monotonic()
            if next_clock_sync is not None and now >= next_clock_sync:
                await asyncio.to_thread(self._client.send_clock_sync, None)
                next_clock_sync = now + self._clock_sync_interval
            if next_interrogation is not None and now >= next_interrogation:
                await asyncio.to_thread(self._client.send_interrogation, None)
                next_interrogation = now + self._general_interrogation_interval
            if next_counter_interrogation is not None and now >= next_counter_interrogation:
                await asyncio.to_thread(self._client.send_counter_interrogation, None)
                next_counter_interrogation = now + self._counter_interrogation_interval

    async def connect(self) -> bool:
        """连接到 IEC104 服务器"""
        try:
            if self._client:
                is_connected = await self._client.connect(timeout=self._connect_timeout)
                self._is_running = is_connected
                if is_connected:
                    self._reconnect_count = 0
                    if self._counter_interrogation_on_connect:
                        await asyncio.to_thread(self._client.send_counter_interrogation, None)
                return is_connected
            return False
        except Exception as e:
            self._is_running = False
            if self._log:
                self._log.error(f"连接 IEC104 服务器失败: {e}")
            return False

    @property
    def last_error(self) -> str:
        return str(getattr(self._client, "last_error", "") or "")

    def disconnect(self) -> None:
        """断开连接"""
        if self._client:
            self._client.disconnect()
            self._is_running = False

    async def _try_reconnect(self) -> bool:
        """按与 Modbus 相同的有界指数退避策略尝试重连。"""
        async with self._reconnect_lock:
            if self.is_running:
                return True

            now = time.monotonic()
            if self._max_reconnect_attempts == 0:
                return False
            if self._max_reconnect_attempts > 0 and self._reconnect_count >= self._max_reconnect_attempts:
                return False

            min_interval = min(
                self._reconnect_initial_interval * (2**self._reconnect_count),
                self._max_reconnect_interval,
            )
            if now - self._last_reconnect_attempt < min_interval:
                return False

            self._last_reconnect_attempt = now
            self._reconnect_count += 1
            if self._log:
                self._log.info(
                    f"尝试重连 IEC104 服务器（第 {self._reconnect_count} 次，当前退避间隔 {min_interval:g} 秒）"
                )

            try:
                await asyncio.to_thread(self.disconnect)
                connected = await self.connect()
                if connected and self._log:
                    self._log.info("IEC104 客户端重连成功")
                return connected
            except Exception as e:
                self._is_running = False
                if self._log:
                    self._log.error(f"IEC104 客户端重连失败: {e}")
                return False

    def _try_reconnect_from_thread(self) -> bool:
        """从数据工作线程将重连协程调度到客户端事件循环。"""
        if not self._loop or not self._loop.is_running():
            return False

        try:
            future = asyncio.run_coroutine_threadsafe(self._try_reconnect(), self._loop)
            return future.result(timeout=self._connect_timeout + 1)
        except Exception as e:
            if self._log:
                self._log.debug(f"IEC104 跨线程重连失败: {e}")
            return False

    @property
    def is_running(self) -> bool:
        """检测客户端的真实连接状态

        重写父类方法，实时检测连接状态。
        当服务端主动断开时，这个属性能反映真实状态。
        """
        if not self._is_running:
            return False

        if not self._client:
            return False

        # 实时检查 IEC104Client 的连接状态（不缓存断开状态）
        if hasattr(self._client, "is_connected") and not self._client.is_connected:
            return False

        # 实时检查所有 c104 station 的连接状态
        if hasattr(self._client, "stations") and self._client.stations:
            for _ca, station in self._client.stations.items():
                if hasattr(station, "is_connected") and not station.is_connected:
                    return False

        return True

    def _get_station_for_point(self, point: BasePoint) -> int:
        """获取测点对应的站地址（common_address）

        Args:
            point: 测点对象

        Returns:
            common_address（即 slave_id）
        """
        return int(point.rtu_addr) if point.rtu_addr else 1

    def read_value(self, point: BasePoint) -> Any:
        """读取测点值

        读取 c104 点的值，c104 库已内部完成类型解码：
        - 归一化类型: float(point.value) 返回 -1~+1 范围的浮点数
        - 标度化类型: float(point.value) 返回标度值
        - 短浮点类型: float(point.value) 返回浮点数

        与 Modbus 一致，c104 返回的值作为协议原始值存入 point.value，
        Yc/Yt 点对象再统一应用 mul_coe/add_coe 计算 real_value。
        """
        # 检查客户端是否已连接（使用 is_running 属性实时检测）
        if not self._client:
            return None
        if not self.is_running and not self._try_reconnect_from_thread():
            if self._log:
                self._log.error("IEC104 客户端未连接")
            return None

        common_address = self._get_station_for_point(point)

        # IEC104 客户端通过 read_point 获取值
        # c104 库已内部完成 ASDU 类型解码。
        c104_value = self._client.read_point(
            io_address=int(point.address),
            frame_type=point.frame_type,
            common_address=common_address,
        )

        # 同步品质描述符（c104.Point.quality 在服务端上报时自动更新）
        try:
            station = self._client.stations.get(common_address)
            if station:
                c104_point = station.get_point(io_address=int(point.address))
                if c104_point and hasattr(c104_point, "quality") and c104_point.quality is not None:
                    from src.enums.points.iec104_quality import decode_quality_from_c104

                    qd = decode_quality_from_c104(c104_point, point.frame_type)
                    point.iec_quality = qd
        except Exception:
            pass

        if c104_value is None:
            if self._log:
                self._log.error(f"IEC104 客户端读取测点值失败 (站={common_address}, IOA={point.address})")
            return None

        if isinstance(point, Yc):
            try:
                return _decode_c104_point_value(point, c104_value)
            except (ValueError, TypeError):
                if self._log:
                    self._log.error(f"IEC104 客户端读取测点值解码失败，地址: {point.address}")
                return None
        return c104_value

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值（发送命令）

        根据 IEC104 ASDU 类型对值进行编码后写入：
        - 归一化类型: 使用 c104.NormalizedFloat
        - 标度化类型: 使用 c104.Int16
        - 短浮点类型: 直接 float
        """
        if not self._client:
            return False
        if not self.is_running and not self._try_reconnect_from_thread():
            return False

        common_address = self._get_station_for_point(point)

        try:
            if isinstance(point, (Yc, Yt)):
                encoded_value = encode_iec104_value(value, point.iec_type_id)
                return self._client.write_point(
                    io_address=int(point.address),
                    value=encoded_value,
                    frame_type=point.frame_type,
                    common_address=common_address,
                )
            elif isinstance(point, (Yx, Yk)):
                return self._client.write_point(
                    io_address=int(point.address),
                    value=bool(value),
                    frame_type=point.frame_type,
                    common_address=common_address,
                )
        except Exception as e:
            if self._log:
                self._log.error(f"IEC104 客户端写入失败: {e}")
            return False

        return False

    async def read_value_async(self, point: BasePoint) -> Any:
        """异步读取测点值（读取本地缓存，不发送网络请求）"""
        if not self._client or (not self.is_running and not await self._try_reconnect()):
            return None
        return self.read_value(point)

    async def send_interrogation(self) -> bool:
        """发送总召唤命令(C_IC_NA_1)到服务器，刷新所有点的缓存值

        发送后需等待服务器响应，c104 库会自动更新本地缓存。
        之后可通过 read_value() 获取最新值。

        Returns:
            bool: 是否成功发送
        """
        if not self._client or (not self.is_running and not await self._try_reconnect()):
            return False
        # 向所有站发送总召唤
        return self._client.send_interrogation(common_address=None)

    async def active_read_value_async(self, point: BasePoint) -> Any:
        """主动读取测点值（发送C_RD_NA_1网络请求获取最新值）

        与 read_value()/read_value_async() 不同，此方法会向服务器
        发送网络请求获取最新值，而非读取本地缓存。

        Args:
            point: 测点对象

        Returns:
            Any: 读取成功返回测点值，失败返回None
        """
        if not self._client or (not self.is_running and not await self._try_reconnect()):
            if self._log:
                self._log.error("IEC104 客户端未连接")
            return None

        common_address = self._get_station_for_point(point)

        # 调用客户端的主动读取方法（发送网络请求）
        c104_value = self._client.active_read_point(
            io_address=int(point.address),
            common_address=common_address,
        )

        # 同步品质描述符
        try:
            station = self._client.stations.get(common_address)
            if station:
                c104_point = station.get_point(io_address=int(point.address))
                if c104_point and hasattr(c104_point, "quality") and c104_point.quality is not None:
                    from src.enums.points.iec104_quality import decode_quality_from_c104

                    qd = decode_quality_from_c104(c104_point, point.frame_type)
                    point.iec_quality = qd
        except Exception:
            pass

        if c104_value is None:
            if self._log:
                self._log.error("IEC104 客户端主动读取测点值失败")
            return None

        if isinstance(point, Yc):
            try:
                return _decode_c104_point_value(point, c104_value)
            except (ValueError, TypeError):
                if self._log:
                    self._log.error(f"IEC104 客户端主动读取测点值解码失败，地址: {point.address}")
                return None
        return c104_value

    async def write_value_async(self, point: BasePoint, value: Any) -> bool:
        """异步写入测点值"""
        if not self._client or (not self.is_running and not await self._try_reconnect()):
            return False
        return self.write_value(point, value)

    def add_points(self, points: list[BasePoint]) -> None:
        """添加测点到 IEC104 客户端

        根据每个测点的 rtu_addr（从机地址）将测点路由到对应的 Station。
        """
        if not self._client:
            return

        for point in points:
            point_type = _resolve_c104_type(point)
            common_address = int(point.rtu_addr) if point.rtu_addr else 1
            self._client.add_point(
                io_address=int(point.address),
                point_type=point_type,
                common_address=common_address,
                command_mode=_resolve_command_mode(point),
            )

    def update_command_mode(self, point: BasePoint, mode: str) -> None:
        if self._client:
            _update_command_mode(self._client.stations, point, mode)

    def update_point_definition(self, point: BasePoint, previous: BasePoint) -> None:
        if self._client:
            _refresh_native_point(self, self._client, point, previous, server=False)

    @property
    def client(self):
        """获取底层客户端对象"""
        return self._client

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取捕获的报文列表"""
        if self._client and hasattr(self._client, "get_captured_messages"):
            return self._client.get_captured_messages(limit)
        return []

    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        if self._client and hasattr(self._client, "clear_captured_messages"):
            self._client.clear_captured_messages()

    def get_avg_time(self) -> dict:
        """获取平均收发时间"""
        if self._client and hasattr(self._client, "message_capture"):
            return self._client.message_capture.get_avg_time()
        return {}
