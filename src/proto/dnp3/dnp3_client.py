"""
DNP3 客户端（Master）封装 —— 纯异步实现

基于 pydnp3_pure 纯 Python asyncio 库，作为主站连接真实 Outstation。
所有网络/协议操作均为 async，由调用方的事件循环驱动（与库的 asyncio 模型一致）。

支持：
- 连接 / 断开（async）
- 完整性轮询、事件轮询（async）
- 主动读取单个测点 / 读缓存
- 遥调（Direct Operate Analog）、遥控（SBO/DO Binary）、未请求使能
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydnp3_pure.app.fragment import AppMessage
from pydnp3_pure.app.layer import ApplicationLayer
from pydnp3_pure.io.tcp_client import TcpClient
from pydnp3_pure.link.frame import LinkFrame
from pydnp3_pure.link.layer import LinkLayer
from pydnp3_pure.master.config import MasterConfig
from pydnp3_pure.master.handler import IMasterHandler
from pydnp3_pure.master.session import MasterSession
from pydnp3_pure.objects.types import CROB
from pydnp3_pure.transport.layer import TransportLayer

from src.config.config import Config
from src.device.core.message.message_capture import MessageCapture


class _MasterHandler(IMasterHandler):
    """Master 响应处理器，缓存最新测点值。"""

    def __init__(self):
        self._values: dict[tuple[int, str], Any] = {}

    def on_response_received(self, message: AppMessage) -> None:
        try:
            for obj in message.objects:
                group = obj.header.group
                for pt in obj.points:
                    key = (group, pt.index)
                    self._values[key] = pt.value
        except Exception:
            pass

    def on_unsolicited_response(self, message: AppMessage) -> None:
        self.on_response_received(message)

    def on_command_complete(self, status) -> None:
        pass

    def on_connection_state_change(self, connected: bool) -> None:
        pass

    def on_timeout(self) -> None:
        pass


class Dnp3Client:
    """DNP3 客户端（Master）—— 纯异步封装"""

    def __init__(self, log=None):
        self._log = log
        self._client: TcpClient | None = None
        self._session: MasterSession | None = None
        self._handler: _MasterHandler | None = None
        self._is_running = False
        self._config: dict[str, Any] = {}
        self._capture = MessageCapture()
        self._address = 0
        self._outstation_address = 1

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

    def _log_warning(self, msg: str) -> None:
        if self._log is None:
            return
        if hasattr(self._log, "warning"):
            self._log.warning(msg)
        elif callable(self._log):
            self._log(msg)

    # ---- 配置 ----

    def set_addresses(self, local_addr: int, outstation_addr: int) -> None:
        """设置本端（Master）地址与对端（Outstation）地址"""
        self._address = int(local_addr)
        self._outstation_address = int(outstation_addr)

    def set_server_port(self, port: int) -> None:
        """设置对端端口（默认 20000）"""
        self._config["port"] = int(port)

    def set_server_ip(self, ip: str) -> None:
        """设置对端 IP"""
        self._config["ip"] = ip

    def set_parameters(self, **kwargs) -> None:
        self._config["runtime"] = {**self._config.get("runtime", {}), **kwargs}

    def set_message_capture(self, capture) -> None:
        self._capture = capture if capture is not None else MessageCapture()

    # ---- 连接 ----

    @property
    def is_connected(self) -> bool:
        return bool(self._client and self._client.is_open)

    def _session_ready(self) -> bool:
        return bool(self._session and self.is_connected)

    async def start(self) -> bool:
        """启动 Master 并连接 Outstation（异步）。"""
        try:
            if self._is_running and self.is_connected:
                return True
            # 客户端(Master)连接目标：空或 0.0.0.0（监听地址）均回退本机
            ip_raw = (self._config.get("ip") or "").strip()
            ip = ip_raw if ip_raw not in ("", "0.0.0.0") else "127.0.0.1"
            if ip_raw in ("", "0.0.0.0"):
                self._log_warning(f"DNP3 客户端目标 IP 无效({ip_raw!r})，已回退 127.0.0.1")
            port = self._config.get(
                "port",
                Config.DNP3_DEFAULT_PORT if hasattr(Config, "DNP3_DEFAULT_PORT") else 20000,
            )
            runtime = self._config.get("runtime", {})

            master_config = MasterConfig(
                address=self._address,
                outstation_address=self._outstation_address,
                integrity_poll_interval_seconds=runtime.get("integrity_interval_s", 60.0),
                event_poll_interval_seconds=runtime.get("event_interval_s", 5.0),
                enable_unsolicited=bool(runtime.get("enable_unsolicited", False)),
                response_timeout_seconds=float(runtime.get("command_timeout_ms", 3000)) / 1000.0,
                max_retries=int(runtime.get("max_retries", 3)),
            )

            self._client = TcpClient(host=ip, port=port)
            self._handler = _MasterHandler()
            self._session = MasterSession(
                config=master_config,
                handler=self._handler,
                send_fragment=lambda f: self._send_fragment(f),
            )

            self._build_stack()
            self._client.set_receive_callback(lambda data: self._on_rx(data))

            await self._client.open()  # open() 内部启动 read_loop 常驻，无需额外保持线程
            self._is_running = True
            self._log_info(f"DNP3 客户端已连接 {ip}:{port}")
            return True
        except Exception as e:
            self._log_error(f"启动 DNP3 客户端失败: {ip}:{port} {e}")
            self._is_running = False
            return False

    async def stop(self) -> bool:
        """停止 Master 并断开连接（异步）。"""
        try:
            self._is_running = False
            if self._client:
                await self._client.close()
            self._client = None
            return True
        except Exception as e:
            self._log_error(f"停止 DNP3 客户端失败: {e}")
            return False

    def is_running(self) -> bool:
        return self._is_running

    # ---- 内部协议层 ----

    def _build_stack(self) -> None:
        transport = TransportLayer(
            on_fragment=lambda f: None,
            send_frame=self._send_frame,
            local_address=self._address,
            remote_address=self._outstation_address,
        )
        app_layer = ApplicationLayer(
            transport=transport,
            on_message=self._session.on_message,
        )
        transport._on_fragment = app_layer.on_fragment_received
        self._link_layer = LinkLayer(on_frame=transport.on_frame_received)
        self._transport = transport

    def _send_frame(self, frame: LinkFrame) -> None:
        if self._client and frame is not None:
            try:
                data = frame.serialize()
                if self._capture:
                    self._capture.add_tx(data)
                self._client.send(data)
            except Exception:
                pass

    def _send_fragment(self, fragment: bytes) -> None:
        if self._transport:
            self._transport.send_fragment(fragment, direction=True)

    def _on_rx(self, data: bytes) -> None:
        if self._capture:
            self._capture.add_rx(data)
        if self._link_layer:
            self._link_layer.data_received(data)

    # ---- 轮询与操作 ----

    async def send_integrity_poll(self) -> bool:
        """发送完整性轮询（读 Class 0 静态数据）。"""
        if not self._session_ready():
            return False
        try:
            await asyncio.get_running_loop().run_in_executor(None, self._session.send_integrity_poll)
            return True
        except Exception:
            return False

    async def send_event_poll(self, classes: tuple[int, ...] = (1, 2, 3)) -> bool:
        """发送事件轮询。"""
        if not self._session_ready():
            return False
        try:
            await asyncio.get_running_loop().run_in_executor(None, lambda: self._session.send_event_poll(classes))
            return True
        except Exception:
            return False

    def read_analog(self, index: int) -> Any:
        """读取遥测值（缓存）。"""
        if self._handler:
            return self._handler._values.get((30, index))
        return None

    def read_binary(self, index: int) -> Any:
        """读取遥信值（缓存）。"""
        if self._handler:
            return self._handler._values.get((1, index))
        return None

    def read_point(self, index: int, group: int, frame_type: int = 0) -> Any:
        """统一读取测点缓存值。"""
        if self._handler:
            return self._handler._values.get((group, index))
        return None

    async def read_point_active(self, index: int, group: int, variation: int = 2) -> Any:
        """主动读取单个测点：触发完整性轮询刷新全局缓存，等待响应后返回指定 index 的最新值。

        说明：pydnp3_pure 的 OutstationSession 不支持解析"指定 index 范围"的 Read 帧
        （会报 index out of bounds），因此退化为按需触发一次完整性轮询（发网络请求
        获取 Outstation 全部静态数据），再从刷新后的缓存中取该 index。语义上仍为
        "点击读取即发请求拿最新值"，非周期后台轮询。
        """
        if not self._session_ready():
            return None
        await self.send_integrity_poll()
        # 短暂等待响应回填缓存（TcpClient 读循环在事件循环内处理响应）
        await asyncio.sleep(0.2)
        return self.read_point(index, group)

    async def write_analog(self, index: int, value: float) -> bool:
        """遥调：发送 Direct Operate 设定值。"""
        if not self._session_ready():
            return False
        try:
            run = asyncio.get_running_loop().run_in_executor
            await run(None, lambda: self._session.send_direct_operate_analog(index=index, value=float(value)))
            return True
        except Exception:
            return False

    async def write_binary(self, index: int, value: bool) -> bool:
        """遥控：发送 Direct Operate（Latch On/Off）。"""
        if not self._session_ready():
            return False
        crob = CROB(control=0x03 if value else 0x01, count=1, on_time_ms=0, off_time_ms=0)
        try:
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: self._session.send_direct_operate_binary(index=index, crob=crob)
            )
            return True
        except Exception:
            return False

    async def operate_binary(self, index: int, value: bool, sbo: bool = False) -> bool:
        """遥控（支持 SBO 两段式或直接操作）。"""
        if sbo:
            if not await self.select_binary(index, value):
                return False
            await asyncio.sleep(0.05)
            return await self.operate_only_binary(index, value)
        return await self.write_binary(index, value)

    async def select_binary(self, index: int, value: bool) -> bool:
        if not self._session_ready():
            return False
        crob = CROB(control=0x03 if value else 0x01, count=1, on_time_ms=0, off_time_ms=0)
        try:
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: self._session.send_select_binary(index=index, crob=crob)
            )
            return True
        except Exception:
            return False

    async def operate_only_binary(self, index: int, value: bool) -> bool:
        if not self._session_ready():
            return False
        crob = CROB(control=0x03 if value else 0x01, count=1, on_time_ms=0, off_time_ms=0)
        try:
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: self._session.send_operate_binary(index=index, crob=crob)
            )
            return True
        except Exception:
            return False

    async def sync_time(self) -> bool:
        """触发时间同步（pydnp3-pure 未暴露显式时间同步，由 Handler 层决定）。"""
        return False

    async def enable_unsolicited(self, enabled: bool = True) -> bool:
        if not self._session_ready():
            return False
        try:
            if enabled:
                await asyncio.get_running_loop().run_in_executor(None, self._session.send_enable_unsolicited)
            else:
                await asyncio.get_running_loop().run_in_executor(None, self._session.send_disable_unsolicited)
            return True
        except Exception:
            return False

    # ---- 报文捕获 ----

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        if self._capture:
            return self._capture.get_messages(limit)
        return []

    def clear_captured_messages(self) -> None:
        if self._capture:
            self._capture.clear()
