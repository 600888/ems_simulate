"""
Modbus 协议处理器
支持 Modbus TCP/RTU 服务端和客户端
"""

import asyncio
from typing import Any, Dict, List, Optional, Union

from src.device.protocol.base_handler import ServerHandler, ClientHandler
from src.enums.points.base_point import BasePoint
from src.enums.point_data import Yc, Yx, Yt, Yk
from src.enums.modbus_def import ProtocolType
from src.enums.modbus_register import Decode
from src.config.config import Config


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

        self._server = ModbusServer(
            self._log, self._slave_id_list, port, protocol_type
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
                point.func_code, slave_id, point.address
            )
        return 0

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值"""
        if self._server and hasattr(point, "func_code"):
            slave_id = point.rtu_addr
            self._server.setValueByAddress(
                point.func_code, slave_id, point.address, value
            )
            return True
        return False

    def add_points(self, points: List[BasePoint]) -> None:
        """添加测点（Modbus 服务器使用地址块方式，无需逐个添加）"""
        pass

    def get_value_by_address(
        self, func_code: int, slave_id: int, address: int
    ) -> Any:
        """根据地址获取值"""
        if self._server:
            return self._server.getValueByAddress(func_code, slave_id, address)
        return 0

    def set_value_by_address(
        self, func_code: int, slave_id: int, address: int, value: Any
    ) -> None:
        """根据地址设置值"""
        if self._server:
            self._server.setValueByAddress(func_code, slave_id, address, value)

    @property
    def server(self):
        """获取底层服务器对象（用于兼容旧代码）"""
        return self._server


class ModbusClientHandler(ClientHandler):
    """Modbus 客户端处理器"""

    def __init__(self, log=None):
        super().__init__()
        self._client = None
        self._log = log

    def initialize(self, config: Dict[str, Any]) -> None:
        """初始化 Modbus 客户端
        
        Args:
            config: 配置字典，包含:
                - ip: 服务器 IP
                - port: 服务器端口
        """
        from src.proto.pyModbus.client import ModbusClient

        self._config = config
        ip = config.get("ip", "127.0.0.1")
        port = config.get("port", Config.DEFAULT_PORT)

        self._client = ModbusClient(ip, port, log=self._log)

    async def start(self) -> bool:
        """启动客户端（连接服务器）"""
        return self.connect()

    async def stop(self) -> bool:
        """停止客户端（断开连接）"""
        self.disconnect()
        return True

    def connect(self) -> bool:
        """连接到 Modbus 服务器"""
        try:
            if self._client:
                self._client.connect()
                self._is_running = True
                return True
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"连接 Modbus 服务器失败: {e}")
            return False

    def disconnect(self) -> None:
        """断开连接"""
        if self._client:
            self._client.disconnect()
            self._is_running = False

    def read_value(self, point: BasePoint) -> Any:
        """读取测点值"""
        if self._client and hasattr(point, "func_code"):
            return self._client.read_value_by_address(
                point.func_code, point.rtu_addr, point.address
            )
        return 0

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值"""
        if self._client and hasattr(point, "func_code"):
            self._client.write_value_by_address(
                point.func_code, point.rtu_addr, point.address, value
            )
            return True
        return False

    def add_points(self, points: List[BasePoint]) -> None:
        """添加测点（Modbus 客户端按需读写，无需预先添加）"""
        pass

    @property
    def client(self):
        """获取底层客户端对象（用于兼容旧代码）"""
        return self._client
