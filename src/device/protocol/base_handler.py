"""
协议处理器基类
定义所有协议处理器的统一接口
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from src.enums.points.base_point import BasePoint
from src.enums.point_data import Yc, Yx, Yt, Yk


class ProtocolHandler(ABC):
    """协议处理器抽象基类"""

    def __init__(self):
        self._is_running: bool = False
        self._config: Dict[str, Any] = {}

    @property
    def is_running(self) -> bool:
        return self._is_running

    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> None:
        """初始化协议处理器
        
        Args:
            config: 配置字典，包含 ip, port, slave_id 等
        """
        pass

    @abstractmethod
    async def start(self) -> bool:
        """启动协议处理器
        
        Returns:
            bool: 启动是否成功
        """
        pass

    @abstractmethod
    async def stop(self) -> bool:
        """停止协议处理器
        
        Returns:
            bool: 停止是否成功
        """
        pass

    @abstractmethod
    def read_value(self, point: BasePoint) -> Any:
        """读取测点值
        
        Args:
            point: 测点对象
            
        Returns:
            读取到的值
        """
        pass

    @abstractmethod
    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值
        
        Args:
            point: 测点对象
            value: 要写入的值
            
        Returns:
            bool: 写入是否成功
        """
        pass

    @abstractmethod
    def add_points(self, points: List[BasePoint]) -> None:
        """添加测点到协议处理器
        
        Args:
            points: 测点列表
        """
        pass

    def set_config(self, key: str, value: Any) -> None:
        """设置配置项"""
        self._config[key] = value

    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self._config.get(key, default)


class ServerHandler(ProtocolHandler):
    """服务端协议处理器基类"""

    @abstractmethod
    def get_value_by_address(
        self, func_code: int, slave_id: int, address: int
    ) -> Any:
        """根据地址获取值"""
        pass

    @abstractmethod
    def set_value_by_address(
        self, func_code: int, slave_id: int, address: int, value: Any
    ) -> None:
        """根据地址设置值"""
        pass


class ClientHandler(ProtocolHandler):
    """客户端协议处理器基类"""

    @abstractmethod
    def connect(self) -> bool:
        """连接到服务器"""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """断开连接"""
        pass
