"""
Modbus 协议处理器
支持 Modbus TCP/RTU 服务端和客户端
"""

import asyncio
import concurrent.futures
from typing import Any, Dict, List, Optional, Union

from src.device.protocol.base_handler import ServerHandler, ClientHandler
from src.enums.points.base_point import BasePoint
from src.enums.point_data import Yc, Yx, Yt, Yk
from src.enums.modbus_def import ProtocolType
from src.enums.modbus_register import Decode
from src.config.config import Config

# 线程池用于执行同步阻塞的 Modbus 操作
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="modbus_client")


class ModbusServerHandler(ServerHandler):
    """Modbus 服务端处理器"""

    def __init__(self, log=None):
        super().__init__()
        self._server = None
        self._log = log
        self._slave_id_list: List[int] = []

    def initialize(self, config: Dict[str, Any]) -> None:
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
        protocol_type = config.get("protocol_type", ProtocolType.ModbusTcp)
        
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
            parity=parity
        )

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

    async def stop(self) -> bool:
        """停止 Modbus 服务器"""
        try:
            if self._server:
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
            return self._server.getValueByAddress(
                point.func_code, slave_id, point.address, point.decode
            )
        return 0

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值"""
        if self._server and hasattr(point, "func_code"):
            slave_id = point.rtu_addr
            self._server.setValueByAddress(
                point.func_code, slave_id, point.address, value, point.decode
            )
            return True

        return False

    async def write_value_async(self, point: BasePoint, value: Any) -> bool:
        """异步写入测点值（包装同步方法）"""
        return self.write_value(point, value)

    def add_points(self, points: List[BasePoint]) -> None:
        """添加测点（Modbus 服务器使用地址块方式，无需逐个添加）"""
        pass

    def get_value_by_address(
        self, func_code: int, slave_id: int, address: int
    ) -> Any:
        """根据地址获取值"""
        if self._server:
            return self._server.getValueByAddress(func_code, slave_id, address) # 这里可能需要默认值或外部传入 decode
        return 0

    def set_value_by_address(
        self, func_code: int, slave_id: int, address: int, value: Any
    ) -> None:
        """根据地址设置值"""
        if self._server:
            self._server.setValueByAddress(func_code, slave_id, address, value) # 这里可能需要默认值或外部传入 decode

    @property
    def server(self):
        """获取底层服务器对象（用于兼容旧代码）"""
        return self._server

    def get_captured_messages(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取捕获的报文列表"""
        if self._server:
            return self._server.getCapturedMessages(limit)
        return []

    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        if self._server:
            self._server.clearCapturedMessages()


class ModbusClientHandler(ClientHandler):
    """Modbus 客户端处理器"""

    def __init__(self, log=None):
        super().__init__()
        self._client = None
        self._log = log
        self._loop = None  # 事件循环引用

    def initialize(self, config: Dict[str, Any]) -> None:
        """初始化 Modbus 客户端
        
        Args:
            config: 配置字典，包含:
                - ip: 服务器 IP
                - port: 服务器端口
        """
        from src.proto.pyModbus.client.modbus_client import ModbusClient
        from src.proto.pyModbus.client.async_client import AsyncModbusClient

        self._config = config
        ip = config.get("ip", "127.0.0.1")
        port = config.get("port", Config.DEFAULT_PORT)
        protocol_type = config.get("protocol_type", ProtocolType.ModbusTcp)
        
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
        if protocol_type == ProtocolType.ModbusTcpClient or protocol_type == ProtocolType.ModbusTcp:
            self._client = AsyncModbusClient(
                host=ip,
                port=port,
                timeout=1.0,
                retries=1,
                log=self._log
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
                log=self._log
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
                if hasattr(self._client, 'connect') and asyncio.iscoroutinefunction(self._client.connect):
                    is_connected = await self._client.connect()
                else:
                    # 同步客户端 (在线程池中执行连接以免阻塞)
                    if self._loop:
                        is_connected = await self._loop.run_in_executor(None, self._client.connect)
                    else:
                        is_connected = self._client.connect()
                
                self._is_running = is_connected
                return is_connected
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"连接 Modbus 服务器失败: {e}")
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        if self._client:
            if hasattr(self._client, 'disconnect') and asyncio.iscoroutinefunction(self._client.disconnect):
                await self._client.disconnect()
            else:
                self._client.disconnect()
            self._is_running = False

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
        if hasattr(self._client, 'connected'):
            if not self._client.connected:
                self._is_running = False
                return False
            
            # 进一步检查底层 pymodbus 客户端的连接状态
            inner_client = getattr(self._client, 'client', None)
            if inner_client and hasattr(inner_client, 'connected'):
                if not inner_client.connected:
                    self._is_running = False
                    self._client.connected = False
                    return False
        
        # 检测同步 ModbusClient 的连接状态
        if hasattr(self._client, 'is_connected'):
            if not self._client.is_connected():
                self._is_running = False
                return False
        
        return True

    def read_value(self, point: BasePoint) -> Any:
        """读取测点值（同步调用，用于 DataUpdateThread 等线程环境）"""
        if not self._client or not hasattr(point, "func_code"):
            return None
        
        # 先检查连接状态，避免不必要的超时等待
        if not self.is_running:
            return None
            
        # 检查是否是异步客户端
        is_async = hasattr(self._client, 'read_value_by_address') and asyncio.iscoroutinefunction(self._client.read_value_by_address)
        
        if is_async:
            # 如果是异步客户端，必须跨线程调用到主事件循环
            if self._loop and self._loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._client.read_value_by_address(
                        point.func_code, point.rtu_addr, point.address, point.decode
                    ),
                    self._loop
                )
                try:
                    return future.result(timeout=1)  # 1秒超时
                except Exception as e:
                    # 单个读取超时不断开连接，只记录日志
                    if self._log:
                        self._log.debug(f"读取超时: {e}")
                    return None
            else:
                return None
        else:
            # 同步客户端直接调用
            return self._client.read_value_by_address(
                point.func_code, point.rtu_addr, point.address, point.decode
            )

    async def read_value_async(self, point: BasePoint) -> Any:
        """异步读取测点值（用于 async 环境）"""
        if not self._client or not hasattr(point, "func_code"):
            return None

        # 检查是否是异步客户端
        is_async = hasattr(self._client, 'read_value_by_address') and asyncio.iscoroutinefunction(self._client.read_value_by_address)

        try:
            if is_async:
                # 使用 asyncio.wait_for 添加超时保护
                return await asyncio.wait_for(
                    self._client.read_value_by_address(
                        point.func_code, point.rtu_addr, point.address, point.decode
                    ),
                    timeout=1.0  # 1秒超时
                )
            else:
                # 同步客户端，放到线程池执行
                loop = asyncio.get_running_loop()
                return await asyncio.wait_for(
                    loop.run_in_executor(
                        None, # 使用默认执行器
                        self._client.read_value_by_address,
                        point.func_code, point.rtu_addr, point.address, point.decode
                    ),
                    timeout=1.0  # 1秒超时
                )
        except asyncio.TimeoutError:
            if self._log:
                self._log.debug(f"异步读取超时: {point.code if hasattr(point, 'code') else point}")
            return None
        except Exception as e:
            if self._log:
                self._log.debug(f"异步读取错误: {e}")
            return None

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值（同步调用）"""
        if not self._client or not hasattr(point, "func_code"):
            return False
            
        # 检查是否是异步客户端
        is_async = hasattr(self._client, 'write_value_by_address') and asyncio.iscoroutinefunction(self._client.write_value_by_address)
        
        if is_async:
            if self._loop and self._loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._client.write_value_by_address(
                        point.func_code, point.rtu_addr, point.address, value, point.decode
                    ),
                    self._loop
                )
                try:
                    return future.result(timeout=2.0)
                except Exception as e:
                    if self._log:
                        self._log.error(f"Async write_value timeout/error: {e}")
                    return False
            return False
        else:
            self._client.write_value_by_address(
                point.func_code, point.rtu_addr, point.address, value, point.decode
            )
            return True

    async def read_value_async(self, point: BasePoint) -> Any:
        """异步读取测点值（用于 async 环境）"""
        if not self._client or not hasattr(point, "func_code"):
            if self._log: self._log.warning(f"read_value_async: client or point invalid. point={point}")
            return None
        
        # 检查是否是异步客户端
        is_async = hasattr(self._client, 'read_value_by_address') and asyncio.iscoroutinefunction(self._client.read_value_by_address)
        
        if self._log: self._log.info(f"read_value_async: point={point.code}, addr={point.address}, func={point.func_code}, is_async={is_async}")

        try:
            if is_async:
                # 使用 asyncio.wait_for 添加超时保护
                return await asyncio.wait_for(
                    self._client.read_value_by_address(
                        point.func_code, point.rtu_addr, point.address, point.decode
                    ),
                    timeout=1.0  # 1秒超时
                )
            else:
                # 同步客户端，放到线程池执行
                loop = asyncio.get_running_loop()
                return await asyncio.wait_for(
                    loop.run_in_executor(
                        None, # 使用默认执行器
                        self._client.read_value_by_address,
                        point.func_code, point.rtu_addr, point.address, point.decode
                    ),
                    timeout=1.0  # 1秒超时
                )
        except asyncio.TimeoutError:
            if self._log:
                self._log.warning(f"Async read_value timeout: {point.code if hasattr(point, 'code') else point}")
            return None
        except Exception as e:
            if self._log:
                self._log.error(f"Async read_value error: {e}")
            return None

    async def write_value_async(self, point: BasePoint, value: Any) -> bool:
        """异步写入测点值（用于 async 环境）"""
        if not self._client or not hasattr(point, "func_code"):
            return False

        # 检查是否是异步客户端
        is_async = hasattr(self._client, 'write_value_by_address') and asyncio.iscoroutinefunction(self._client.write_value_by_address)

        try:
            if is_async:
                # 使用 asyncio.wait_for 添加超时保护
                return await asyncio.wait_for(
                    self._client.write_value_by_address(
                        point.func_code, point.rtu_addr, point.address, value, point.decode
                    ),
                    timeout=2.0  # 2秒超时
                )
            else:
                # 同步客户端，放到线程池执行
                loop = asyncio.get_running_loop()
                return await asyncio.wait_for(
                    loop.run_in_executor(
                        None, # 使用默认执行器
                        self._client.write_value_by_address,
                        point.func_code, point.rtu_addr, point.address, value, point.decode
                    ),
                    timeout=2.0  # 2秒超时
                )
        except asyncio.TimeoutError:
            if self._log:
                self._log.error(f"Async write_value timeout: {point.code if hasattr(point, 'code') else point}")
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"Async write_value error: {e}")
            return False

    def add_points(self, points: List[BasePoint]) -> None:
        """添加测点（Modbus 客户端按需读写，无需预先添加）"""
        pass

    @property
    def client(self):
        """获取底层客户端对象（用于兼容旧代码）"""
        return self._client

    def get_captured_messages(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取捕获的报文列表"""
        if self._client:
            return self._client.getCapturedMessages(limit)
        return []

    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        if self._client:
            self._client.clearCapturedMessages()
