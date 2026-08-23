"""
DNP3 服务端（Outstation）封装

基于 pydnp3_pure 纯 Python 库，通过 TCP 监听 Master 连接，
响应完整性轮询、读请求与 SBO/DO 控制。

与 src/proto/iec104/iec104server.py 的封装风格保持一致。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydnp3_pure.app.constants import CommandStatus
from pydnp3_pure.app.layer import ApplicationLayer
from pydnp3_pure.link.frame import LinkFrame
from pydnp3_pure.link.layer import LinkLayer
from pydnp3_pure.objects.types import CROB
from pydnp3_pure.outstation.config import OutstationConfig
from pydnp3_pure.outstation.database import PointConfig, PointDatabase
from pydnp3_pure.outstation.handler import IOutstationHandler
from pydnp3_pure.outstation.session import OutstationSession
from pydnp3_pure.transport.layer import TransportLayer

from src.config.config import Config
from src.device.core.message.message_capture import MessageCapture
from src.proto.dnp3.tracked_tcp_server import TrackedTcpServer


class _OutstationHandler(IOutstationHandler):
    """处理 Master 下发的控制命令（遥调/遥控），同步更新点对象值。"""

    def __init__(self, server: Dnp3Server, database: PointDatabase):
        self._server = server
        self._db = database
        self.on_command_callback: Callable[[int, Any, int], None] | None = None

    # 遥控（Binary Output）
    def on_direct_operate_binary(self, index: int, crob: CROB) -> CommandStatus:
        value = int(crob.is_latch_on)
        pts = self._db.get_binary_outputs()
        if any(p.index == index for p in pts):
            self._db.update_binary_output(index, bool(crob.is_latch_on))
        self._server._notify_command(2, index, value)
        return CommandStatus.SUCCESS

    def on_select_binary(self, index: int, crob: CROB) -> CommandStatus:
        # SBO 第一步：选择（暂不执行）
        return CommandStatus.SUCCESS

    def on_operate_binary(self, index: int, crob: CROB) -> CommandStatus:
        value = int(crob.is_latch_on)
        pts = self._db.get_binary_outputs()
        if any(p.index == index for p in pts):
            self._db.update_binary_output(index, bool(crob.is_latch_on))
        self._server._notify_command(2, index, value)
        return CommandStatus.SUCCESS

    # 遥调（Analog Output）
    def on_direct_operate_analog(self, index: int, value: float) -> CommandStatus:
        pts = self._db.get_analog_outputs()
        if any(p.index == index for p in pts):
            self._db.update_analog_output(index, value)
        self._server._notify_command(3, index, value)
        return CommandStatus.SUCCESS

    def on_select_analog(self, index: int, value: float) -> CommandStatus:
        return CommandStatus.SUCCESS

    def on_operate_analog(self, index: int, value: float) -> CommandStatus:
        pts = self._db.get_analog_outputs()
        if any(p.index == index for p in pts):
            self._db.update_analog_output(index, value)
        self._server._notify_command(3, index, value)
        return CommandStatus.SUCCESS

    def on_freeze(self) -> None:
        pass

    def on_cold_restart(self) -> int:
        return 0

    def on_warm_restart(self) -> int:
        return 0


class Dnp3Server:
    """DNP3 服务端（Outstation）"""

    def __init__(self, log=None):
        super().__init__()
        self._log = log  # 由 Handler 传入的 logger（loguru Logger 或可调用对象）
        self._server: TrackedTcpServer | None = None
        self._session: OutstationSession | None = None
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

    def _log_info(self, msg: str) -> None:
        if self._log is None:
            return
        if hasattr(self._log, "info"):
            self._log.info(msg)
        elif callable(self._log):
            self._log(msg)

    def _log_error(self, msg: str) -> None:
        if self._log is None:
            return
        if hasattr(self._log, "error"):
            self._log.error(msg)
        elif callable(self._log):
            self._log(msg)

    # ---- 配置 ----

    def set_addresses(self, local_addr: int, master_addr: int) -> None:
        """设置本端（Outstation）地址与对端（Master）地址"""
        self._address = int(local_addr)
        self._master_address = int(master_addr)

    def set_connection_callbacks(self, *, on_connect=None, on_activity=None, on_disconnect=None) -> None:
        self._on_connection_opened = on_connect
        self._on_connection_activity = on_activity
        self._on_connection_closed = on_disconnect

    def set_server_port(self, port: int) -> None:
        """设置 TCP 监听端口（默认 20000）"""
        self._config["port"] = int(port)

    def set_server_ip(self, ip: str) -> None:
        """设置监听 IP（默认 0.0.0.0）"""
        self._config["ip"] = ip

    def set_parameters(self, **kwargs) -> None:
        """设置运行参数：
        enable_unsolicited, class_events_max, select_timeout_seconds 等
        """
        self._config["runtime"] = {**self._config.get("runtime", {}), **kwargs}

    def set_message_capture(self, capture) -> None:
        """设置报文捕获器（由 Handler 注入）"""
        self._capture = capture if capture is not None else MessageCapture()

    # ---- 测点注册 ----

    def add_analog_input(self, index: int, deadband: float = 0.0, event_class: int = 1) -> None:
        """注册遥测（G30/G32 Analog Input）"""
        self._db.add_analog_input(
            int(index),
            0.0,
            config=PointConfig(event_class=event_class, deadband=deadband),
        )

    def add_binary_input(self, index: int, event_class: int = 1) -> None:
        """注册遥信（G1/G2 Binary Input）"""
        self._db.add_binary_input(
            int(index),
            False,
            config=PointConfig(event_class=event_class),
        )

    def add_analog_output(self, index: int) -> None:
        """注册遥调（G40 Analog Output）"""
        self._db.add_analog_output(int(index), 0.0)

    def add_binary_output(self, index: int) -> None:
        """注册遥控（G10/G12 Binary Output）"""
        self._db.add_binary_output(int(index), False)

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
        for p in self._db.get_analog_inputs():
            if p.index == index:
                return p.value
        return None

    def get_binary_input(self, index: int) -> bool | None:
        for p in self._db.get_binary_inputs():
            if p.index == index:
                return bool(p.value)
        return None

    def get_analog_output(self, index: int) -> float | None:
        for p in self._db.get_analog_outputs():
            if p.index == index:
                return p.value
        return None

    def get_binary_output(self, index: int) -> bool | None:
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
                on_connect=self._on_connection_opened,
                on_activity=self._on_connection_activity,
                on_disconnect=self._on_connection_closed,
            )
            handler = _OutstationHandler(self, self._db)
            self._session = OutstationSession(
                config=outstation_config,
                database=self._db,
                handler=handler,
                send_fragment=lambda f: self._send_fragment(f),
            )

            self._build_stack()
            self._server.set_receive_callback(lambda data: self._on_rx(data))

            await self._server.open()  # 注册监听，返回后由事件循环持续处理客户端连接
            self._is_running = True
            self._log_info(f"DNP3 服务端已监听 {ip}:{port} (address={self._address})")
            return True
        except Exception as e:
            self._log_error(f"启动 DNP3 服务端失败: {e}")
            self._is_running = False
            return False

    def _build_stack(self) -> None:
        """组装 link/transport/application 协议栈"""
        transport = TransportLayer(
            on_fragment=lambda f: None,
            send_frame=self._send_frame,
            local_address=self._address,
            remote_address=self._master_address,
        )
        app_layer = ApplicationLayer(
            transport=transport,
            on_message=self._session.on_message,
        )
        transport._on_fragment = app_layer.on_fragment_received
        self._link_layer = LinkLayer(on_frame=transport.on_frame_received)
        self._transport = transport
        # 链路层连接/发送：Master 请求直接由 session 处理，fragment 发送走 transport

    def _send_frame(self, frame: LinkFrame) -> None:
        if self._server and frame is not None:
            try:
                data = frame.serialize()
                if self._capture:
                    self._capture.add_tx(data)
                self._server.send(data)
            except Exception:
                pass

    def _send_fragment(self, fragment: bytes) -> None:
        if self._transport:
            self._transport.send_fragment(fragment, direction=False)

    def _on_rx(self, data: bytes) -> None:
        if self._capture:
            self._capture.add_rx(data)
        if self._link_layer:
            self._link_layer.data_received(data)

    async def stop(self) -> bool:
        """停止 DNP3 服务端（异步）。"""
        try:
            self._is_running = False
            if self._server:
                await self._server.close()
            self._server = None
            return True
        except Exception as e:
            self._log_error(f"停止 DNP3 服务端失败: {e}")
            return False

    def is_running(self) -> bool:
        return self._is_running

    # ---- 报文捕获 ----

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        if self._capture:
            return self._capture.get_messages(limit)
        return []

    def clear_captured_messages(self) -> None:
        if self._capture:
            self._capture.clear()
