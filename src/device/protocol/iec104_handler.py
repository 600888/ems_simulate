"""
IEC104 协议处理器
支持 IEC104 服务端和客户端
"""

from typing import Any, Dict, List, Optional
import c104

from src.device.protocol.base_handler import ServerHandler, ClientHandler
from src.enums.points.base_point import BasePoint
from src.enums.point_data import Yc, Yx, Yt, Yk
from src.config.config import Config


class IEC104ServerHandler(ServerHandler):
    """IEC104 服务端处理器"""

    def __init__(self, log=None):
        super().__init__()
        self._server = None
        self._log = log

    def initialize(self, config: Dict[str, Any]) -> None:
        """初始化 IEC104 服务器
        
        Args:
            config: 配置字典，包含:
                - ip: 监听 IP（默认 0.0.0.0）
                - port: 监听端口（默认 2404）
                - common_address: 站地址（默认 1）
        """
        from src.proto.iec104.iec104server import IEC104Server

        self._config = config
        ip = config.get("ip", Config.DEFAULT_IP)
        port = config.get("port", Config.IEC104_DEFAULT_PORT)
        common_address = config.get("common_address", 1)

        self._server:IEC104Server = IEC104Server(ip=ip, port=port, common_address=common_address)

    async def start(self) -> bool:
        """启动 IEC104 服务器"""
        try:
            if self._server:
                self._server.start()
                self._is_running = True
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
                self._server.stop()
                self._is_running = False
                return True
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"停止 IEC104 服务器失败: {e}")
            return False

    def read_value(self, point: BasePoint) -> Any:
        """读取测点值"""
        if self._server:
            return self._server.get_point_value(
                io_address=point.address, frame_type=point.frame_type
            )
        return 0

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值"""
        if self._server:
            self._server.set_point_value(
                io_address=point.address,
                value=value,
                frame_type=point.frame_type,
            )
            return True
        return False

    def add_points(self, points: List[BasePoint]) -> None:
        """添加测点到 IEC104 服务器"""
        if not self._server:
            return

        for point in points:
            frame_type = point.frame_type
            if frame_type == 0:  # 遥测
                self._server.add_monitoring_point(
                    io_address=point.address,
                    point_type=c104.Type.M_ME_NC_1,
                )
            elif frame_type == 1:  # 遥信
                self._server.add_monitoring_point(
                    io_address=point.address,
                    point_type=c104.Type.M_SP_NA_1,
                )
            elif frame_type == 2:  # 遥控
                self._server.add_command_point(
                    io_address=point.address,
                    point_type=c104.Type.C_SC_NA_1,
                )
            elif frame_type == 3:  # 遥调
                self._server.add_command_point(
                    io_address=point.address,
                    point_type=c104.Type.C_SE_NC_1,
                )

    def get_value_by_address(
        self, func_code: int, slave_id: int, address: int
    ) -> Any:
        """根据地址获取值"""
        if self._server:
            return self._server.get_point_value(io_address=address, frame_type=0)
        return 0

    def set_value_by_address(
        self, func_code: int, slave_id: int, address: int, value: Any
    ) -> None:
        """根据地址设置值"""
        if self._server:
            self._server.set_point_value(io_address=address, value=value, frame_type=0)

    @property
    def server(self):
        """获取底层服务器对象"""
        return self._server

    def get_captured_messages(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取捕获的报文列表"""
        if self._server and hasattr(self._server, 'get_captured_messages'):
            return self._server.get_captured_messages(limit)
        return []

    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        if self._server and hasattr(self._server, 'clear_captured_messages'):
            self._server.clear_captured_messages()


class IEC104ClientHandler(ClientHandler):
    """IEC104 客户端处理器"""

    def __init__(self, log=None):
        super().__init__()
        self._client = None
        self._log = log

    def initialize(self, config: Dict[str, Any]) -> None:
        """初始化 IEC104 客户端
        
        Args:
            config: 配置字典，包含:
                - ip: 服务器 IP
                - port: 服务器端口（默认 2404）
                - common_address: 站地址（默认 1）
        """
        from src.proto.iec104.iec104client import IEC104Client

        self._config = config
        ip = config.get("ip", "127.0.0.1")
        port = config.get("port", Config.IEC104_DEFAULT_PORT)
        common_address = config.get("common_address", 1)

        self._client = IEC104Client(ip=ip, port=port, common_address=common_address)

    async def start(self) -> bool:
        """启动客户端（连接服务器）"""
        return self.connect()

    async def stop(self) -> bool:
        """停止客户端（断开连接）"""
        self.disconnect()
        return True

    def connect(self) -> bool:
        """连接到 IEC104 服务器"""
        try:
            if self._client:
                self._client.connect()
                self._is_running = True
                return True
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"连接 IEC104 服务器失败: {e}")
            return False

    def disconnect(self) -> None:
        """断开连接"""
        if self._client:
            self._client.disconnect()
            self._is_running = False

    def read_value(self, point: BasePoint) -> Any:
        """读取测点值"""
        if self._client:
            # IEC104 客户端通过 read_point 获取物理值
            real_val = self._client.read_point(
                io_address=point.address, frame_type=point.frame_type
            )
            if real_val is None:
                return 0
            
            # 如果是遥测点，需要根据系数反向换算回寄存器/原始值
            # 这样 store 进 point.value 后，系统显示的 real_value 才会正确
            if isinstance(point, Yc):
                try:
                    return int((real_val - point.add_coe) / point.mul_coe)
                except (ZeroDivisionError, TypeError):
                    return 0
            return real_val
        return 0

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值（发送命令）"""
        if self._client:
            # 客户端写入：将内部原始值换算为物理值发送给外部设备
            real_to_send = value
            if isinstance(point, Yc):
                real_to_send = value * point.mul_coe + point.add_coe
            
            return self._client.write_point(
                io_address=point.address,
                value=float(real_to_send),
                frame_type=point.frame_type
            )
        return False

    def add_points(self, points: List[BasePoint]) -> None:
        """添加测点到 IEC104 客户端"""
        if not self._client:
            return

        for point in points:
            frame_type = point.frame_type
            if frame_type == 0:  # 遥测
                self._client.add_point(
                    io_address=point.address,
                    point_type=c104.Type.M_ME_NC_1,
                )
            elif frame_type == 1:  # 遥信
                self._client.add_point(
                    io_address=point.address,
                    point_type=c104.Type.M_SP_NA_1,
                )
            elif frame_type == 2:  # 遥控
                self._client.add_point(
                    io_address=point.address,
                    point_type=c104.Type.C_SC_NA_1,
                )
            elif frame_type == 3:  # 遥调
                self._client.add_point(
                    io_address=point.address,
                    point_type=c104.Type.C_SE_NC_1,
                )

    @property
    def client(self):
        """获取底层客户端对象"""
        return self._client

    def get_captured_messages(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取捕获的报文列表"""
        if self._client and hasattr(self._client, 'get_captured_messages'):
            return self._client.get_captured_messages(limit)
        return []

    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        if self._client and hasattr(self._client, 'clear_captured_messages'):
            self._client.clear_captured_messages()
