"""
DNP3 服务端（Outstation）封装

基于 pydnp3_pure 纯 Python 库，通过 TCP 监听 Master 连接，
响应完整性轮询、读请求与 SBO/DO 控制。

与 src/proto/iec104/iec104server.py 的封装风格保持一致。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import math
import ssl
import time
from typing import Any

from pydnp3_pure.app.constants import CommandStatus, ControlCode
from pydnp3_pure.link.frame import LinkFrame
from pydnp3_pure.link.layer import LinkLayer
from pydnp3_pure.objects.types import CROB
from pydnp3_pure.outstation.config import OutstationConfig
from pydnp3_pure.outstation.database import PointConfig, PointDatabase
from pydnp3_pure.outstation.handler import IOutstationHandler
from pydnp3_pure.transport.layer import TransportLayer

from src.config.config import Config
from src.device.core.message.message_capture import MessageCapture
from src.proto.dnp3.application import parse_application_fragment
from src.proto.dnp3.outstation_session import ReliableOutstationSession
from src.proto.dnp3.point_config import Dnp3PointConfig
from src.proto.dnp3.reliable_link import ReliableLinkEndpoint
from src.proto.dnp3.tracked_tcp_server import TrackedTcpServer
from src.proto.dnp3.wire import FragmentCorrelator, WireFrameExtractor, accepts_link_address


class _OutstationHandler(IOutstationHandler):
    """处理 Master 下发的控制命令（遥调/遥控），同步更新点对象值。"""

    def __init__(self, server: Dnp3Server, database: PointDatabase, select_timeout_seconds: float):
        self._server = server
        self._db = database
        self._select_timeout_seconds = select_timeout_seconds
        self._selections: dict[tuple[str, int], tuple[tuple[Any, ...], float]] = {}
        self.on_command_callback: Callable[[int, Any, int], None] | None = None

    @staticmethod
    def _binary_value(crob: CROB) -> bool:
        """将 CROB 命令解析为二进制输出的目标值。"""
        return bool(crob.is_latch_on or crob.is_pulse_on)

    @staticmethod
    def _binary_command_valid(crob: CROB) -> bool:
        """校验 CROB 命令类型受支持且次数为正。"""
        return (
            crob.op_type
            in {
                ControlCode.PULSE_ON,
                ControlCode.PULSE_OFF,
                ControlCode.LATCH_ON,
                ControlCode.LATCH_OFF,
            }
            and crob.count > 0
        )

    @staticmethod
    def _binary_signature(crob: CROB) -> tuple[Any, ...]:
        """生成 CROB 命令的签名，用于选择/操作匹配校验。"""
        return (crob.control, crob.count, crob.on_time_ms, crob.off_time_ms)

    def _selected(self, kind: str, index: int, signature: tuple[Any, ...]) -> bool:
        """校验并消费一次有效的选择记录。"""
        selected = self._selections.pop((kind, index), None)
        return bool(selected and selected[0] == signature and selected[1] >= time.monotonic())

    def clear_selections(self) -> None:
        """清空所有待选择记录。"""
        self._selections.clear()

    def _prune_expired_selections(self) -> None:
        """清理已过期的选择记录。"""
        now = time.monotonic()
        self._selections = {key: selected for key, selected in self._selections.items() if selected[1] >= now}

    # 遥控（Binary Output）
    def on_direct_operate_binary(self, index: int, crob: CROB) -> CommandStatus:
        """处理直接操作遥控：未选择模式下立即执行并更新输出。"""
        if self._server.point_config(2, index).control_mode == "sbo":
            return CommandStatus.NO_SELECT
        if not self._binary_command_valid(crob):
            return CommandStatus.FORMAT_ERROR
        pts = self._db.get_binary_outputs()
        if not any(p.index == index for p in pts):
            return CommandStatus.OUT_OF_RANGE
        value = self._binary_value(crob)
        self._db.update_binary_output(index, value)
        self._server._notify_command(2, index, int(value))
        return CommandStatus.SUCCESS

    def on_select_binary(self, index: int, crob: CROB) -> CommandStatus:
        """处理遥控选择：记录命令签名与有效期。"""
        if not self._binary_command_valid(crob):
            return CommandStatus.FORMAT_ERROR
        if not any(point.index == index for point in self._db.get_binary_outputs()):
            return CommandStatus.OUT_OF_RANGE
        self._prune_expired_selections()
        self._selections[("binary", index)] = (
            self._binary_signature(crob),
            time.monotonic() + self._select_timeout_seconds,
        )
        return CommandStatus.SUCCESS

    def on_operate_binary(self, index: int, crob: CROB) -> CommandStatus:
        """处理遥控操作：匹配选择记录后执行并更新输出。"""
        if not self._binary_command_valid(crob):
            return CommandStatus.FORMAT_ERROR
        if not self._selected("binary", index, self._binary_signature(crob)):
            return CommandStatus.NO_SELECT
        value = self._binary_value(crob)
        self._db.update_binary_output(index, value)
        self._server._notify_command(2, index, int(value))
        return CommandStatus.SUCCESS

    # 遥调（Analog Output）
    def on_direct_operate_analog(self, index: int, value: float) -> CommandStatus:
        """处理直接操作遥调：未选择模式下立即执行并更新输出。"""
        if self._server.point_config(3, index).control_mode == "sbo":
            return CommandStatus.NO_SELECT
        if not math.isfinite(value):
            return CommandStatus.FORMAT_ERROR
        pts = self._db.get_analog_outputs()
        if not any(p.index == index for p in pts):
            return CommandStatus.OUT_OF_RANGE
        self._db.update_analog_output(index, value)
        self._server._notify_command(3, index, value)
        return CommandStatus.SUCCESS

    def on_select_analog(self, index: int, value: float) -> CommandStatus:
        """处理遥调选择：记录目标值与有效期。"""
        if not math.isfinite(value):
            return CommandStatus.FORMAT_ERROR
        if not any(point.index == index for point in self._db.get_analog_outputs()):
            return CommandStatus.OUT_OF_RANGE
        self._prune_expired_selections()
        self._selections[("analog", index)] = (
            (float(value),),
            time.monotonic() + self._select_timeout_seconds,
        )
        return CommandStatus.SUCCESS

    def on_operate_analog(self, index: int, value: float) -> CommandStatus:
        """处理遥调操作：匹配选择记录后执行并更新输出。"""
        if not math.isfinite(value):
            return CommandStatus.FORMAT_ERROR
        if not self._selected("analog", index, (float(value),)):
            return CommandStatus.NO_SELECT
        self._db.update_analog_output(index, value)
        self._server._notify_command(3, index, value)
        return CommandStatus.SUCCESS

    def on_freeze(self) -> None:
        """处理冻结请求的通告（当前实现无额外动作）。"""
        pass

    def on_cold_restart(self) -> int:
        """返回冷重启所需的延迟秒数。"""
        return 0

    def on_warm_restart(self) -> int:
        """返回热重启所需的延迟秒数。"""
        return 0


class Dnp3Server:
    """DNP3 服务端（Outstation）"""

    def __init__(self, log=None):
        super().__init__()
        self._log = log  # 由 Handler 传入的 logger（loguru Logger 或可调用对象）
        self._server: TrackedTcpServer | None = None
        self._ssl_context: ssl.SSLContext | None = None
        self._session: ReliableOutstationSession | None = None
        self._outstation_handler: _OutstationHandler | None = None
        self._db = PointDatabase()
        self._is_running = False
        self._config: dict[str, Any] = {}
        self._capture = MessageCapture()
        self._on_command_callback: Callable[[int, Any, int], None] | None = None
        self._address = 1
        self._master_address = 0
        self._on_connection_opened = None
        self._on_connection_activity = None
        self._on_connection_closed = None
        self._wire_capture = WireFrameExtractor(self._capture_rx_frame)
        self._rx_fragments = FragmentCorrelator("dnp3-rx")
        self._tx_fragments = FragmentCorrelator("dnp3-tx")
        self._loop: asyncio.AbstractEventLoop | None = None
        self._link_endpoint: ReliableLinkEndpoint | None = None
        self._point_configs: dict[tuple[int, int], Dnp3PointConfig] = {}

    def _log_info(self, msg: str) -> None:
        """以 info 级别记录日志。"""
        if self._log is None:
            return
        if hasattr(self._log, "info"):
            self._log.info(msg)
        elif callable(self._log):
            self._log(msg)

    def _log_error(self, msg: str) -> None:
        """以 error 级别记录日志。"""
        if self._log is None:
            return
        if hasattr(self._log, "error"):
            self._log.error(msg)
        elif callable(self._log):
            self._log(msg)

    # ---- 配置 ----

    def set_addresses(self, local_addr: int, master_addr: int) -> None:
        """设置本端（Outstation）地址与对端（Master）地址"""
        self._address = self._validate_index(local_addr, "Outstation地址")
        self._master_address = self._validate_index(master_addr, "Master地址")

    @staticmethod
    def _validate_index(index: int, label: str = "点索引") -> int:
        """校验地址/索引必须在 0 到 65535 之间，否则抛出异常。"""
        value = int(index)
        if not 0 <= value <= 0xFFFF:
            raise ValueError(f"DNP3{label}必须在 0 到 65535 之间: {value}")
        return value

    def set_connection_callbacks(self, *, on_connect=None, on_activity=None, on_disconnect=None) -> None:
        """注册连接打开、活动与断开的回调。"""
        self._on_connection_opened = on_connect
        self._on_connection_activity = on_activity
        self._on_connection_closed = on_disconnect

    def set_server_port(self, port: int) -> None:
        """设置 TCP 监听端口（默认 20000）"""
        self._config["port"] = int(port)

    def set_server_ip(self, ip: str) -> None:
        """设置监听 IP（默认 0.0.0.0）"""
        self._config["ip"] = ip

    def set_ssl_context(self, context: ssl.SSLContext | None) -> None:
        """Set the optional TLS context used by the TCP listener."""
        self._ssl_context = context

    @property
    def connection_security(self) -> dict[str, object]:
        """Return security metadata for the active Master connection."""
        return self._server.security if self._server else {"tls": False}

    def set_parameters(self, **kwargs) -> None:
        """设置运行参数：
        enable_unsolicited, class_events_max, select_timeout_seconds 等
        """
        self._config["runtime"] = {**self._config.get("runtime", {}), **kwargs}

    def set_message_capture(self, capture) -> None:
        """设置报文捕获器（由 Handler 注入）"""
        self._capture = capture if capture is not None else MessageCapture()
        self._wire_capture = WireFrameExtractor(self._capture_rx_frame)
        self._rx_fragments.reset()
        self._tx_fragments.reset()

    # ---- 测点注册 ----

    def add_analog_input(
        self,
        index: int,
        deadband: float = 0.0,
        event_class: int = 1,
        dnp3_config: dict[str, Any] | None = None,
    ) -> None:
        """注册遥测（G30/G32 Analog Input）"""
        index = self._validate_index(index)
        config = Dnp3PointConfig.from_mapping(0, dnp3_config)
        if dnp3_config is None:
            config.deadband = deadband
            config.event_class = event_class
        db_config = PointConfig(
            event_class=config.event_class,
            deadband=config.deadband,
            default_variation=config.static_variation,
        )
        db_config.event_variation = config.event_variation
        db_config.event_enabled = config.event_enabled
        db_config.timestamp_enabled = config.timestamp_enabled
        self._db.add_analog_input(
            index,
            0.0,
            config=db_config,
        )
        self._point_configs[(0, index)] = config
        self._db.get_analog_inputs(index, index)[0].flags = config.initial_quality

    def add_binary_input(
        self,
        index: int,
        event_class: int = 1,
        dnp3_config: dict[str, Any] | None = None,
    ) -> None:
        """注册遥信（G1/G2 Binary Input）"""
        index = self._validate_index(index)
        config = Dnp3PointConfig.from_mapping(1, dnp3_config)
        if dnp3_config is None:
            config.event_class = event_class
        db_config = PointConfig(event_class=config.event_class, default_variation=config.static_variation)
        db_config.event_variation = config.event_variation
        db_config.event_enabled = config.event_enabled
        db_config.timestamp_enabled = config.timestamp_enabled
        self._db.add_binary_input(
            index,
            False,
            config=db_config,
        )
        self._point_configs[(1, index)] = config
        self._db.get_binary_inputs(index, index)[0].flags = config.initial_quality

    def add_analog_output(self, index: int, dnp3_config: dict[str, Any] | None = None) -> None:
        """注册遥调（G40 Analog Output）"""
        index = self._validate_index(index)
        config = Dnp3PointConfig.from_mapping(3, dnp3_config)
        self._db.add_analog_output(index, 0.0)
        self._point_configs[(3, index)] = config
        self._db.get_analog_outputs(index, index)[0].flags = config.initial_quality

    def add_binary_output(self, index: int, dnp3_config: dict[str, Any] | None = None) -> None:
        """注册遥控（G10/G12 Binary Output）"""
        index = self._validate_index(index)
        config = Dnp3PointConfig.from_mapping(2, dnp3_config)
        self._db.add_binary_output(index, False)
        self._point_configs[(2, index)] = config
        self._db.get_binary_outputs(index, index)[0].flags = config.initial_quality

    def point_config(self, frame_type: int, index: int) -> Dnp3PointConfig:
        """获取指定类型的测点配置，缺失时返回默认配置。"""
        return self._point_configs.get((frame_type, index), Dnp3PointConfig.defaults(frame_type))

    # ---- 值读写 ----

    def update_analog_input(self, index: int, value: float, quality: int = 0) -> None:
        """更新遥测值（变化超过死区会产生事件）"""
        flags = 0x01 if quality == 0 else int(quality)  # ONLINE=1
        self._db.update_analog_input(int(index), float(value), flags=flags)

    def update_binary_input(self, index: int, value: bool, quality: int = 0) -> None:
        """更新遥信值"""
        flags = 0x01 if quality == 0 else int(quality)
        self._db.update_binary_input(int(index), bool(value), flags=flags)

    def get_analog_input(self, index: int) -> float | None:
        """读取遥测（模拟量输入）当前值。"""
        for p in self._db.get_analog_inputs():
            if p.index == index:
                return p.value
        return None

    def get_binary_input(self, index: int) -> bool | None:
        """读取遥信（二进制输入）当前值。"""
        for p in self._db.get_binary_inputs():
            if p.index == index:
                return bool(p.value)
        return None

    def get_analog_output(self, index: int) -> float | None:
        """读取遥调（模拟量输出）当前值。"""
        for p in self._db.get_analog_outputs():
            if p.index == index:
                return p.value
        return None

    def get_binary_output(self, index: int) -> bool | None:
        """读取遥控（二进制输出）当前值。"""
        for p in self._db.get_binary_outputs():
            if p.index == index:
                return bool(p.value)
        return None

    def get_point_value(self, index: int, frame_type: int = 0) -> Any:
        """统一读取测点值（frame_type: 0=遥测,1=遥信,2=遥控,3=遥调）"""
        if frame_type == 0:
            return self.get_analog_input(index)
        if frame_type == 1:
            return self.get_binary_input(index)
        if frame_type == 2:
            return self.get_binary_output(index)
        if frame_type == 3:
            return self.get_analog_output(index)
        return None

    def set_point_value(self, index: int, value, frame_type: int = 0) -> None:
        """统一写入测点值（frame_type: 0=遥测,1=遥信,2=遥控,3=遥调）"""
        if frame_type == 0:
            self.update_analog_input(index, float(value))
        elif frame_type == 1:
            self.update_binary_input(index, bool(value))
        elif frame_type == 2:
            self.update_binary_output(index, bool(value))
        elif frame_type == 3:
            self.update_analog_output(index, float(value))

    def update_binary_output(self, index: int, value: bool, quality: int = 0) -> None:
        """更新遥控（输出）值"""
        pts = self._db.get_binary_outputs()
        if any(p.index == index for p in pts):
            flags = 0x01 if quality == 0 else int(quality)
            self._db.update_binary_output(int(index), bool(value), flags=flags)

    def update_analog_output(self, index: int, value: float, quality: int = 0) -> None:
        """更新遥调（输出）值"""
        pts = self._db.get_analog_outputs()
        if any(p.index == index for p in pts):
            flags = 0x01 if quality == 0 else int(quality)
            self._db.update_analog_output(int(index), float(value), flags=flags)

    # ---- 命令回调 ----

    def set_on_command_callback(self, callback) -> None:
        """注册遥控/遥调命令接收回调 callback(frame_type, index, value)"""
        self._on_command_callback = callback

    def _notify_command(self, frame_type: int, index: int, value: Any) -> None:
        """将收到的遥控/遥调命令通知给注册的上层回调。"""
        if self._on_command_callback:
            try:
                self._on_command_callback(index, value, frame_type)
            except Exception as e:
                self._log_error(f"调用命令回调失败: {e}")

    # ---- 生命周期 ----

    async def start(self) -> bool:
        """启动 DNP3 服务端（异步）。TcpServer.open 注册监听后立即返回，连接由事件循环持续处理。"""
        try:
            if self._is_running:
                return True
            port = self._config.get("port", Config.DNP3_DEFAULT_PORT if hasattr(Config, "DNP3_DEFAULT_PORT") else 20000)
            ip = (self._config.get("ip") or "").strip() or Config.DEFAULT_IP
            runtime = self._config.get("runtime", {})
            self._loop = asyncio.get_running_loop()

            outstation_config = OutstationConfig(
                address=self._address,
                master_address=self._master_address,
                enable_unsolicited=bool(runtime.get("enable_unsolicited", False)),
                class_1_events_max=int(runtime.get("class_1_events_max", runtime.get("event_buffer_size", 1000))),
                class_2_events_max=int(runtime.get("class_2_events_max", runtime.get("event_buffer_size", 1000))),
                class_3_events_max=int(runtime.get("class_3_events_max", runtime.get("event_buffer_size", 1000))),
                select_timeout_seconds=float(runtime.get("select_timeout_s", 10.0)),
            )

            self._server = TrackedTcpServer(
                host=ip,
                port=port,
                ssl_context=self._ssl_context,
                on_connect=self._handle_connection_opened,
                on_activity=self._on_connection_activity,
                on_disconnect=self._on_connection_closed,
            )
            handler = _OutstationHandler(self, self._db, outstation_config.select_timeout_seconds)
            self._outstation_handler = handler
            self._session = ReliableOutstationSession(
                config=outstation_config,
                database=self._db,
                handler=handler,
                send_fragment=lambda f: self._send_fragment(f),
                app_confirm=bool(runtime.get("app_confirm", True)),
                confirm_timeout_seconds=float(runtime.get("confirm_timeout_ms", 5000)) / 1000.0,
                max_confirm_retries=int(runtime.get("confirm_max_retries", 2)),
                request_unsolicited_send=self._schedule_unsolicited,
            )

            self._build_stack()
            self._server.set_receive_callback(lambda data: self._on_rx(data))

            await self._server.open()  # 注册监听，返回后由事件循环持续处理客户端连接
            self._is_running = True
            transport = "TLS" if self._ssl_context else "TCP"
            self._log_info(f"DNP3 服务端已通过 {transport} 监听 {ip}:{port} (address={self._address})")
            return True
        except Exception as e:
            self._log_error(f"启动 DNP3 服务端失败: {e}")
            self._is_running = False
            return False

    def _handle_connection_opened(self, key, remote_endpoint, local_endpoint) -> None:
        """连接建立时复位协议栈与选择记录，并通知回调。"""
        if self._link_layer:
            self._link_layer.reset()
        if self._link_endpoint:
            self._link_endpoint.reset()
        if self._transport:
            self._transport.reset()
        self._wire_capture.reset()
        self._rx_fragments.reset()
        self._tx_fragments.reset()
        if self._outstation_handler:
            self._outstation_handler.clear_selections()
        if self._session:
            self._session.on_connection_opened()
        if self._on_connection_opened:
            self._on_connection_opened(key, remote_endpoint, local_endpoint)

    def _schedule_unsolicited(self) -> None:
        """在线程安全环境下调度发送一次未请求上报。"""
        if self._loop is None or not self._session:
            return
        self._loop.call_soon_threadsafe(self._session.send_unsolicited)

    def _build_stack(self) -> None:
        """组装 link/transport/application 协议栈"""
        transport = TransportLayer(
            on_fragment=lambda f: None,
            send_frame=self._send_frame,
            local_address=self._address,
            remote_address=self._master_address,
        )
        transport._on_fragment = self._on_fragment
        self._link_layer = LinkLayer(on_frame=self._on_link_frame)
        runtime = self._config.get("runtime", {})
        self._link_endpoint = ReliableLinkEndpoint(
            enabled=bool(runtime.get("link_confirm", False)),
            local_is_master=False,
            write_frame=self._write_frame,
            deliver_frame=self._deliver_link_frame,
            timeout_seconds=float(runtime.get("link_confirm_timeout_ms", 1000)) / 1000.0,
            max_retries=int(runtime.get("link_confirm_max_retries", 2)),
            on_error=self._log_error,
        )
        self._transport = transport
        # 链路层连接/发送：Master 请求直接由 session 处理，fragment 发送走 transport

    def _send_frame(self, frame: LinkFrame) -> None:
        """发送链路帧（启用确认时交由可靠链路端点处理）。"""
        if self._link_endpoint:
            self._link_endpoint.send(frame)
        else:
            self._write_frame(frame)

    def _write_frame(self, frame: LinkFrame) -> None:
        """将链路帧序列化并经 TCP 发送，同时记录发送报文。"""
        if self._server and frame is not None:
            try:
                data = frame.serialize()
                if self._capture:
                    self._capture.add_tx(data, self._tx_fragments.metadata(data))
                self._server.send(data)
            except (ConnectionError, OSError, RuntimeError) as exc:
                self._log_error(f"DNP3服务端发送链路帧失败: {exc}")

    def _send_fragment(self, fragment: bytes) -> None:
        """将应用层分段交给传输层发送。"""
        if self._transport:
            self._transport.send_fragment(fragment, direction=False)

    def _on_rx(self, data: bytes) -> None:
        """处理 TCP 原始接收数据，交给链路层解析。"""
        try:
            self._wire_capture.data_received(data)
            if self._link_layer:
                self._link_layer.data_received(data)
        except Exception as exc:
            self._log_error(f"DNP3服务端接收报文处理失败: {exc}")

    def _capture_rx_frame(self, raw: bytes) -> None:
        """记录接收到的原始链路帧。"""
        if self._capture:
            self._capture.add_rx(raw, self._rx_fragments.metadata(raw))

    def _on_link_frame(self, frame: LinkFrame) -> None:
        """接收链路帧：校验地址匹配后交由可靠链路端点处理。"""
        if not accepts_link_address(
            frame.header.destination,
            frame.header.source,
            local=self._address,
            remote=self._master_address,
        ):
            self._log_error(f"忽略地址不匹配的DNP3帧: src={frame.header.source}, dst={frame.header.destination}")
            return
        if self._link_endpoint:
            self._link_endpoint.on_frame(frame)

    def _deliver_link_frame(self, frame: LinkFrame) -> None:
        """将链路帧送入传输层处理。"""
        if self._transport:
            self._transport.on_frame_received(frame)

    def _on_fragment(self, fragment: bytes) -> None:
        """解析应用层分段并交给会话层处理。"""
        if not self._session:
            return
        try:
            self._session.on_message(parse_application_fragment(fragment))
        except (IndexError, ValueError) as exc:
            self._log_error(f"DNP3应用报文解析失败: {exc}")

    async def stop(self) -> bool:
        """停止 DNP3 服务端（异步）。"""
        try:
            self._is_running = False
            if self._session:
                self._session.close()
            if self._server:
                await self._server.close()
            self._server = None
            self._session = None
            self._outstation_handler = None
            self._transport = None
            self._link_layer = None
            if self._link_endpoint:
                self._link_endpoint.reset()
            self._link_endpoint = None
            self._wire_capture.reset()
            self._rx_fragments.reset()
            self._tx_fragments.reset()
            self._loop = None
            return True
        except Exception as e:
            self._log_error(f"停止 DNP3 服务端失败: {e}")
            return False

    def is_running(self) -> bool:
        """服务端是否处于运行状态。"""
        return self._is_running

    # ---- 报文捕获 ----

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取捕获的收发报文列表。"""
        if self._capture:
            return self._capture.get_messages(limit)
        return []

    def clear_captured_messages(self) -> None:
        """清空捕获的报文。"""
        if self._capture:
            self._capture.clear()
