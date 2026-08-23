"""
Modbus 协议处理器
支持 Modbus TCP/RTU 服务端和客户端
"""

import asyncio
import concurrent.futures
import time
from typing import Any

from src.config.config import Config
from src.device.core.connection import DisconnectInitiator, DisconnectReason
from src.device.protocol.base_handler import ClientHandler, ServerHandler
from src.enums.modbus_def import ProtocolType
from src.enums.points.base_point import BasePoint
from src.enums.points.change_tracker import ChangeSource, get_current_client_info, track_change

# 线程池用于执行同步阻塞的 Modbus 操作
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="modbus_client")


class ModbusServerHandler(ServerHandler):
    """Modbus 服务端处理器"""

    def __init__(self, log=None):
        super().__init__()
        self._server = None
        self._log = log
        self._slave_id_list: list[int] = []
        self._points: list[BasePoint] = []

    def initialize(self, config: dict[str, Any]) -> None:
        """初始化 Modbus 服务器

        Args:
            config: 配置字典，包含:
                - port: 服务端口
                - slave_id_list: 从机 ID 列表
                - protocol_type: 协议类型 (ModbusTcp/ModbusRtu)
        """
        from src.proto.pyModbus.server import ModbusServer

        self._config = config
        port = config.get("port", Config.DEFAULT_PORT)
        self._slave_id_list = config.get("slave_id_list", [1])
        protocol_type = config.get("protocol_type", ProtocolType.ModbusTcpServer)
        self._configure_connection_monitoring(
            config,
            supported=protocol_type in (ProtocolType.ModbusTcpServer, ProtocolType.ModbusRtuOverTcp),
        )
        security = config.get("security", {})
        runtime = config.get("runtime", {})

        # 串口配置
        serial_port = config.get("serial_port", "COM1")
        baudrate = config.get("baudrate", 9600)
        bytesize = config.get("databits", 8)
        stopbits = config.get("stopbits", 1)
        parity = config.get("parity", "N")

        if self._log:
            self._log.info(f"Modbus 服务端初始化: port={port}, slave_id_list={self._slave_id_list}")

        self._server = ModbusServer(
            logger=self._log,
            slave_id_list=self._slave_id_list,
            port=port,
            protocol_type=protocol_type,
            serial_port=serial_port,
            baudrate=baudrate,
            bytesize=bytesize,
            stopbits=stopbits,
            parity=parity,
            tls_enabled=bool(security.get("tls_enabled")),
            tls_mode=str(security.get("tls_mode") or "one_way"),
            certificate_path=security.get("certificate_path"),
            private_key_path=security.get("private_key_path"),
            ca_certificate_path=security.get("ca_certificate_path"),
            client_idle_timeout=runtime.get("client_idle_timeout_ms", 0) / 1000,
            max_connections=runtime.get("max_connections", 0),
            on_connection_opened=self._on_connection_opened,
            on_connection_activity=self._on_connection_activity,
            on_connection_closed=self._on_connection_closed,
        )
        # 设置回调函数，用于处理来自 Modbus 客户端的写入请求，记录测点变化日志
        self._server.on_write_callback = self._on_modbus_client_write

    async def start(self) -> bool:
        """启动 Modbus 服务器"""
        try:
            if self._server:
                asyncio.create_task(self._server.start())
                self._is_running = True
                return True
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"启动 Modbus 服务器失败: {e}")
            return False

    def _on_connection_opened(self, key, remote_endpoint, local_endpoint, security) -> None:
        self._open_connection(
            key,
            remote_endpoint=remote_endpoint,
            local_endpoint=local_endpoint,
            security=security,
        )

    def _on_connection_activity(self, key, size: int) -> None:
        self._record_connection_activity(key, rx_bytes=size, rx_messages=1)

    def _on_connection_closed(self, key, reason: str, detail: str | None) -> None:
        reason_map = {
            "remote_closed": (DisconnectReason.REMOTE_CLOSED, DisconnectInitiator.REMOTE),
            "network_reset": (DisconnectReason.NETWORK_RESET, DisconnectInitiator.NETWORK),
            "idle_timeout": (DisconnectReason.IDLE_TIMEOUT, DisconnectInitiator.SERVER),
        }
        normalized, initiator = reason_map.get(
            reason,
            (DisconnectReason.UNKNOWN, DisconnectInitiator.UNKNOWN),
        )
        self._close_connection(key, reason=normalized, initiator=initiator, detail=detail)

    async def stop(self) -> bool:
        """停止 Modbus 服务器"""
        try:
            if self._server:
                self._close_all_connections()
                await self._server.stopAsync()
                self._is_running = False
                return True
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"停止 Modbus 服务器失败: {e}")
            return False

    def read_value(self, point: BasePoint) -> Any:
        """读取测点值"""
        if self._server and hasattr(point, "func_code"):
            slave_id = point.rtu_addr
            val = self._server.getValueByAddress(point.func_code, slave_id, point.address, point.decode)
            bit_offset = getattr(point, "bit", None)
            if bit_offset is not None and val is not None:
                try:
                    return int(bool((int(val) >> bit_offset) & 1))
                except (ValueError, TypeError):
                    pass
            return val
        return 0

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值"""
        if self._server and hasattr(point, "func_code"):
            slave_id = point.rtu_addr
            write_val = value
            bit_offset = getattr(point, "bit", None)
            if bit_offset is not None:
                cur_val = self._server.getValueByAddress(point.func_code, slave_id, point.address, point.decode)
                if cur_val is not None:
                    try:
                        cur_int = int(cur_val)
                        write_val = cur_int | 1 << bit_offset if int(value) else cur_int & ~(1 << bit_offset)
                    except (ValueError, TypeError):
                        pass

            self._server.setValueByAddress(point.func_code, slave_id, point.address, write_val, point.decode)
            self._log.info(f"写入测点 {point.code} 成功: value={write_val}")
            return True

        return False

    async def write_value_async(self, point: BasePoint, value: Any) -> bool:
        """异步写入测点值（包装同步方法）"""
        return self.write_value(point, value)

    def add_points(self, points: list[BasePoint]) -> None:
        """添加测点"""
        for p in points:
            if p not in self._points:
                self._points.append(p)

    def _on_modbus_client_write(self, slave_id: int, fx: int, address: int, values: list[int]) -> None:
        """处理来自 Modbus 客户端的写入请求，并同步回设备测点"""
        if not self._points:
            return

        # 根据功能码判断是否支持
        if fx not in (5, 6, 15, 16):
            return

        write_start_addr = address
        write_end_addr = address + len(values) - 1

        for point in self._points:
            if getattr(point, "rtu_addr", None) == slave_id:
                # 检查功能码是否匹配 (保持寄存器 3, 6, 16 -> 修改时 fx 为 6 或 16)
                # (线圈 1, 5, 15 -> 修改时 fx 为 5 或 15)
                is_holding_reg = (point.func_code in (3, 6, 16)) and (fx in (6, 16))
                is_coil = (point.func_code in (1, 5, 15)) and (fx in (5, 15))

                if is_holding_reg or is_coil:
                    # 计算测点占据的寄存器范围
                    # Decode.get_decode_register_cnt 可以获取寄存器数，向后兼容 hasattr
                    point_start_addr = point.address
                    if hasattr(point, "register_cnt"):
                        point_end_addr = point.address + point.register_cnt - 1
                    else:
                        from src.enums.modbus_register import Decode

                        point_end_addr = (
                            point.address + Decode.get_decode_register_cnt(getattr(point, "decode", "0x41")) - 1
                        )

                    # 判断地址是否有交集
                    if max(point_start_addr, write_start_addr) <= min(point_end_addr, write_end_addr):
                        # 重新读取点位值并设置
                        new_value = self.read_value(point)
                        if new_value is not None:
                            client_info = get_current_client_info() or "未知客户端"
                            with track_change(ChangeSource.PROTOCOL, f"Modbus客户端远程写入 {point.code}", client_info):
                                point.value = new_value

    def get_value_by_address(self, func_code: int, slave_id: int, address: int) -> Any:
        """根据地址获取值"""
        if self._server:
            return self._server.getValueByAddress(func_code, slave_id, address)  # 这里可能需要默认值或外部传入 decode
        return 0

    def set_value_by_address(self, func_code: int, slave_id: int, address: int, value: Any) -> None:
        """根据地址设置值"""
        if self._server:
            self._server.setValueByAddress(func_code, slave_id, address, value)

    @property
    def server(self):
        """获取底层服务器对象（用于兼容旧代码）"""
        return self._server

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取捕获的报文列表"""
        if self._server:
            return self._server.getCapturedMessages(limit)
        return []

    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        if self._server:
            self._server.clearCapturedMessages()

    def get_avg_time(self) -> dict:
        """获取平均收发时间"""
        if self._server and hasattr(self._server, "message_capture"):
            return self._server.message_capture.get_avg_time()
        return {}


class ModbusClientHandler(ClientHandler):
    """Modbus 客户端处理器"""

    def __init__(self, log=None):
        super().__init__()
        self._client = None
        self._log = log
        self._reconnect_initial_interval = 2.0
        self._max_reconnect_attempts = 0
        self._command_timeout = 2.0
        self._loop = None  # 事件循环引用
        # 重连相关状态
        self._reconnect_count = 0  # 连续重连尝试次数
        self._last_reconnect_attempt = 0.0  # 上次重连尝试时间戳
        self._max_reconnect_interval = 30  # 最大重连间隔（秒）

    def initialize(self, config: dict[str, Any]) -> None:
        """初始化 Modbus 客户端

        Args:
            config: 配置字典，包含:
                - ip: 服务器 IP
                - port: 服务器端口
        """
        from src.proto.pyModbus.client.async_client import AsyncModbusClient
        from src.proto.pyModbus.client.modbus_client import ModbusClient

        self._config = config
        ip = config.get("ip", "127.0.0.1")
        port = config.get("port", Config.DEFAULT_PORT)
        protocol_type = config.get("protocol_type", ProtocolType.ModbusTcpServer)
        runtime = config.get("runtime", {})
        security = config.get("security", {})
        self._command_timeout = runtime.get("command_timeout_ms", 2000) / 1000
        self._reconnect_initial_interval = runtime.get("reconnect_initial_interval_ms", 2000) / 1000
        self._max_reconnect_interval = runtime.get("reconnect_max_interval_ms", 30000) / 1000
        self._max_reconnect_attempts = runtime.get("reconnect_max_attempts", 0)
        connect_timeout = runtime.get("connect_timeout_ms", 3000) / 1000
        retries = runtime.get("command_retry_count", 1)

        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

        # 串口配置
        serial_port = config.get("serial_port", "COM1")
        baudrate = config.get("baudrate", 9600)
        bytesize = config.get("databits", 8)
        stopbits = config.get("stopbits", 1)
        parity = config.get("parity", "N")

        # 对于 TCP 客户端，使用专门的异步客户端以避免同一进程中的阻塞
        if protocol_type == ProtocolType.ModbusTcpClient or protocol_type == ProtocolType.ModbusTcpServer:
            self._client = AsyncModbusClient(
                host=ip,
                port=port,
                timeout=connect_timeout,
                retries=retries,
                tls_enabled=bool(security.get("tls_enabled")),
                tls_mode=str(security.get("tls_mode") or "one_way"),
                certificate_path=security.get("certificate_path"),
                private_key_path=security.get("private_key_path"),
                ca_certificate_path=security.get("ca_certificate_path"),
                log=self._log,
            )
        else:
            self._client = ModbusClient(
                host=ip,
                port=port,
                protocol_type=protocol_type,
                serial_port=serial_port,
                baudrate=baudrate,
                bytesize=bytesize,
                stopbits=stopbits,
                parity=parity,
                log=self._log,
            )

    async def start(self) -> bool:
        """启动客户端（连接服务器）"""
        return await self.connect()

    async def stop(self) -> bool:
        """停止客户端（断开连接）"""
        await self.disconnect()
        return True

    async def connect(self) -> bool:
        """连接到 Modbus 服务器"""
        try:
            if self._client:
                # 检查是否是异步客户端
                if hasattr(self._client, "connect") and asyncio.iscoroutinefunction(self._client.connect):
                    is_connected = await self._client.connect()
                else:
                    # 同步客户端 (在线程池中执行连接以免阻塞)
                    if self._loop:
                        is_connected = await self._loop.run_in_executor(None, self._client.connect)
                    else:
                        is_connected = self._client.connect()

                self._is_running = is_connected
                if is_connected:
                    self._reconnect_count = 0  # 连接成功，重置退避计数器
                return is_connected
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"连接 Modbus 服务器失败: {e}")
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        if self._client:
            if hasattr(self._client, "disconnect") and asyncio.iscoroutinefunction(self._client.disconnect):
                await self._client.disconnect()
            else:
                self._client.disconnect()
            self._is_running = False

    async def _try_reconnect(self) -> bool:
        """尝试自动重连（带指数退避冷却机制）

        当检测到连接断开时调用，避免无限重试导致日志刷屏。
        退避策略：2^reconnect_count 秒，上限 _max_reconnect_interval 秒。
        重连成功后重置计数器。

        Returns:
            bool: 重连是否成功
        """
        now = time.time()
        # 指数退避：2, 4, 8, 16, 30, 30, 30...
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
                f"尝试重连 Modbus 服务器 (第{self._reconnect_count}次, "
                f"下次间隔{min(2**self._reconnect_count, self._max_reconnect_interval)}秒)..."
            )

        try:
            # 先断开旧连接（清理残留状态）
            await self.disconnect()
            # 重新初始化客户端（创建新的底层连接对象）
            self.initialize(self._config)
            # 尝试连接
            connected = await self.connect()
            if connected:
                self._reconnect_count = 0  # 重置退避计数器
                if self._log:
                    self._log.info("Modbus 客户端重连成功")
                return True
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"重连失败: {e}")
            return False

    def _try_reconnect_from_thread(self) -> bool:
        """从非事件循环线程尝试自动重连（同步版本）

        用于 read_value() 等同步方法中，当检测到连接断开时，
        通过 run_coroutine_threadsafe() 调度重连协程到主事件循环。

        Returns:
            bool: 重连是否成功
        """
        now = time.time()
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

        if not self._loop or not self._loop.is_running():
            return False

        try:
            future = asyncio.run_coroutine_threadsafe(self._try_reconnect(), self._loop)
            return future.result(timeout=self._connection_timeout)
        except Exception as e:
            if self._log:
                self._log.debug(f"跨线程重连失败: {e}")
            return False

    @property
    def is_running(self) -> bool:
        """检测客户端的真实连接状态

        重写父类方法，实时检测连接状态而不只是返回标志位。
        当服务端主动断开时，这个属性能反映真实状态。
        """
        if not self._is_running:
            return False

        if not self._client:
            return False

        # 检测 AsyncModbusClient 的连接状态
        if hasattr(self._client, "connected"):
            if not self._client.connected:
                self._is_running = False
                return False

            # 进一步检查底层 pymodbus 客户端的连接状态
            inner_client = getattr(self._client, "client", None)
            if inner_client and hasattr(inner_client, "connected") and not inner_client.connected:
                self._is_running = False
                self._client.connected = False
                return False

        # 检测同步 ModbusClient 的连接状态
        if hasattr(self._client, "is_connected") and not self._client.is_connected():
            self._is_running = False
            return False

        return True

    def read_value(self, point: BasePoint) -> Any:
        """读取测点值（同步调用，用于 DataUpdateThread 等线程环境）"""
        if not self._client or not hasattr(point, "func_code"):
            return None

        # 先检查连接状态，避免不必要的超时等待
        if not self.is_running:
            # 尝试跨线程自动重连
            if not self._try_reconnect_from_thread():
                return None

        # 检查是否是异步客户端
        is_async = hasattr(self._client, "read_value_by_address") and asyncio.iscoroutinefunction(
            self._client.read_value_by_address
        )

        if is_async:
            # 如果是异步客户端，必须跨线程调用到主事件循环
            if self._loop and self._loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._client.read_value_by_address(point.func_code, point.rtu_addr, point.address, point.decode),
                    self._loop,
                )
                try:
                    val = future.result(timeout=self._command_timeout)
                except Exception as e:
                    # 单个读取超时不断开连接，只记录日志
                    if self._log:
                        self._log.debug(f"读取超时: {e}")
                    return None
            else:
                return None
        else:
            # 同步客户端直接调用
            val = self._client.read_value_by_address(point.func_code, point.rtu_addr, point.address, point.decode)

        bit_offset = getattr(point, "bit", None)
        if bit_offset is not None and val is not None:
            try:
                return int(bool((int(val) >> bit_offset) & 1))
            except (ValueError, TypeError):
                pass
        return val

    async def read_value_async(self, point: BasePoint) -> Any:
        """异步读取测点值（用于 async 环境）"""
        if not self._client or not hasattr(point, "func_code"):
            return None

        # 连接断开时尝试自动重连
        if not self.is_running and not await self._try_reconnect():
            return None

        # 检查是否是异步客户端
        is_async = hasattr(self._client, "read_value_by_address") and asyncio.iscoroutinefunction(
            self._client.read_value_by_address
        )

        try:
            if is_async:
                # 使用 asyncio.wait_for 添加超时保护
                val = await asyncio.wait_for(
                    self._client.read_value_by_address(point.func_code, point.rtu_addr, point.address, point.decode),
                    timeout=self._command_timeout,
                )
            else:
                # 同步客户端，放到线程池执行
                loop = asyncio.get_running_loop()
                val = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,  # 使用默认执行器
                        self._client.read_value_by_address,
                        point.func_code,
                        point.rtu_addr,
                        point.address,
                        point.decode,
                    ),
                    timeout=self._command_timeout,
                )
            bit_offset = getattr(point, "bit", None)
            if bit_offset is not None and val is not None:
                try:
                    return int(bool((int(val) >> bit_offset) & 1))
                except (ValueError, TypeError):
                    pass
            return val
        except TimeoutError:
            if self._log:
                self._log.debug(f"异步读取超时: {point.code if hasattr(point, 'code') else point}")
            return None
        except Exception as e:
            if self._log:
                self._log.debug(f"异步读取错误: {e}")
            return None

    async def read_registers_batch_async(
        self, func_code: int, slave_id: int, start_address: int, count: int
    ) -> list[int]:
        """批量读取连续寄存器（优化方法）

        Args:
            func_code: 功能码 (1=线圈, 2=离散输入, 3=保持寄存器, 4=输入寄存器)
            slave_id: 从站地址
            start_address: 起始寄存器地址
            count: 读取的寄存器数量

        Returns:
            寄存器值列表，失败返回空列表
        """
        if not self._client:
            return []

        if not self.is_running:
            # 连接断开，尝试自动重连
            if not await self._try_reconnect():
                return []

        # 检查是否是异步客户端
        is_async_client = hasattr(self._client, "read_holding_registers") and asyncio.iscoroutinefunction(
            self._client.read_holding_registers
        )

        try:
            if is_async_client:
                # 异步客户端
                return await asyncio.wait_for(
                    self._read_registers_by_func_code_async(func_code, slave_id, start_address, count),
                    timeout=self._command_timeout,
                )
            else:
                # 同步客户端，放到线程池执行
                loop = asyncio.get_running_loop()
                return await asyncio.wait_for(
                    loop.run_in_executor(
                        None, self._read_registers_by_func_code_sync, func_code, slave_id, start_address, count
                    ),
                    timeout=self._command_timeout,
                )
        except TimeoutError:
            if self._log:
                self._log.warning(f"批量读取超时: slave={slave_id}, addr={start_address}, count={count}")
            return []
        except Exception as e:
            if self._log:
                self._log.error(f"批量读取错误: {e}")
            return []

    async def _read_registers_by_func_code_async(
        self, func_code: int, slave_id: int, start_address: int, count: int
    ) -> list[int]:
        """根据功能码异步读取寄存器"""
        if func_code in (3, 6, 16):  # 保持寄存器
            return await self._client.read_holding_registers(slave_id, start_address, count)
        elif func_code == 4:  # 输入寄存器
            return await self._client.read_input_registers(slave_id, start_address, count)
        elif func_code in (1, 5, 15):  # 线圈
            return await self._client.read_coils(slave_id, start_address, count)
        elif func_code == 2:  # 离散输入
            return await self._client.read_discrete_inputs(slave_id, start_address, count)
        else:
            if self._log:
                self._log.warning(f"不支持的功能码批量读取: {func_code}")
            return []

    def _read_registers_by_func_code_sync(
        self, func_code: int, slave_id: int, start_address: int, count: int
    ) -> list[int]:
        """根据功能码同步读取寄存器"""
        if func_code in (3, 6, 16):  # 保持寄存器
            return self._client.read_holding_registers(slave_id, start_address, count)
        elif func_code == 4:  # 输入寄存器
            return self._client.read_input_registers(slave_id, start_address, count)
        elif func_code in (1, 5, 15):  # 线圈
            return self._client.read_coils(slave_id, start_address, count)
        elif func_code == 2:  # 离散输入
            return self._client.read_discrete_inputs(slave_id, start_address, count)
        else:
            if self._log:
                self._log.warning(f"不支持的功能码批量读取: {func_code}")
            return []

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值（同步调用）"""
        if not self._client or not hasattr(point, "func_code"):
            return False

        # 检查是否是异步客户端
        is_async = hasattr(self._client, "write_value_by_address") and asyncio.iscoroutinefunction(
            self._client.write_value_by_address
        )

        if is_async:
            if self._loop and self._loop.is_running():

                async def _do_write():
                    write_val = value
                    bit_offset = getattr(point, "bit", None)
                    if bit_offset is not None:
                        cur_val = await self._client.read_value_by_address(
                            point.func_code, point.rtu_addr, point.address, point.decode
                        )
                        if cur_val is not None:
                            try:
                                cur_int = int(cur_val)
                                write_val = cur_int | 1 << bit_offset if int(value) else cur_int & ~(1 << bit_offset)
                            except (ValueError, TypeError):
                                pass
                    return await self._client.write_value_by_address(
                        point.func_code, point.rtu_addr, point.address, write_val, point.decode
                    )

                future = asyncio.run_coroutine_threadsafe(_do_write(), self._loop)
                try:
                    return future.result(timeout=self._command_timeout)
                except concurrent.futures.TimeoutError:
                    if self._log:
                        self._log.warning(f"写入测试超时: {point.code}")
                    return False
                except Exception as e:
                    if self._log:
                        self._log.error(f"写入测点 {point.code} 失败: {e}")
                    return False
            return False
        else:
            write_val = value
            bit_offset = getattr(point, "bit", None)
            if bit_offset is not None:
                cur_val = self._client.read_value_by_address(
                    point.func_code, point.rtu_addr, point.address, point.decode
                )
                if cur_val is not None:
                    try:
                        cur_int = int(cur_val)
                        write_val = cur_int | 1 << bit_offset if int(value) else cur_int & ~(1 << bit_offset)
                    except (ValueError, TypeError):
                        pass

            self._client.write_value_by_address(point.func_code, point.rtu_addr, point.address, write_val, point.decode)
            return True

    async def write_value_async(self, point: BasePoint, value: Any) -> bool:
        """异步写入测点值（用于 async 环境）"""
        if not self._client or not hasattr(point, "func_code"):
            return False

        # 检查是否是异步客户端
        is_async = hasattr(self._client, "write_value_by_address") and asyncio.iscoroutinefunction(
            self._client.write_value_by_address
        )

        write_val = value
        bit_offset = getattr(point, "bit", None)

        if is_async:
            if bit_offset is not None:
                cur_val = await self._client.read_value_by_address(
                    point.func_code, point.rtu_addr, point.address, point.decode
                )
                if cur_val is not None:
                    try:
                        cur_int = int(cur_val)
                        write_val = cur_int | 1 << bit_offset if int(value) else cur_int & ~(1 << bit_offset)
                    except (ValueError, TypeError):
                        pass

            return await asyncio.wait_for(
                self._client.write_value_by_address(
                    point.func_code, point.rtu_addr, point.address, write_val, point.decode
                ),
                timeout=self._command_timeout,
            )
        else:
            # 同步客户端，放到线程池执行
            loop = asyncio.get_running_loop()

            def _sync_write():
                w_val = value
                if bit_offset is not None:
                    cur_val = self._client.read_value_by_address(
                        point.func_code, point.rtu_addr, point.address, point.decode
                    )
                    if cur_val is not None:
                        try:
                            cur_int = int(cur_val)
                            w_val = cur_int | 1 << bit_offset if int(value) else cur_int & ~(1 << bit_offset)
                        except (ValueError, TypeError):
                            pass
                self._client.write_value_by_address(point.func_code, point.rtu_addr, point.address, w_val, point.decode)
                return True

            return await asyncio.wait_for(loop.run_in_executor(None, _sync_write), timeout=self._command_timeout)

    def add_points(self, points: list[BasePoint]) -> None:
        """添加测点（Modbus 客户端按需读写，无需预先添加）"""
        pass

    @property
    def client(self):
        """获取底层客户端对象（用于兼容旧代码）"""
        return self._client

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取捕获的报文列表"""
        if self._client:
            return self._client.getCapturedMessages(limit)
        return []

    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        if self._client:
            self._client.clearCapturedMessages()

    def get_avg_time(self) -> dict:
        """获取平均收发时间"""
        if self._client and hasattr(self._client, "message_capture"):
            return self._client.message_capture.get_avg_time()
        return {}
