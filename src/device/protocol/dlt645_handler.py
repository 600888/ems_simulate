"""
DLT645 协议处理器
支持 DLT645 电力表计协议服务端
"""

from typing import Any, Dict, List, Optional

from src.device.protocol.base_handler import ServerHandler
from src.enums.points.base_point import BasePoint


class DLT645ServerHandler(ServerHandler):
    """DLT645 服务端处理器"""

    def __init__(self, log=None):
        super().__init__()
        self._server = None
        self._log = log
        self._meter_address: str = "000000000000"

    def initialize(self, config: Dict[str, Any]) -> None:
        """初始化 DLT645 服务器
        
        Args:
            config: 配置字典，包含:
                - ip: 监听 IP（默认 0.0.0.0）
                - port: 监听端口
                - meter_address: 电表地址（12位BCD码）
                - timeout: 超时时间（默认 30）
        """
        from dlt645.service.serversvc.server_service import MeterServerService

        self._config = config
        ip = config.get("ip", "0.0.0.0")
        port = config.get("port", 8899)
        timeout = config.get("timeout", 30)
        self._meter_address:str = config.get("meter_address", "000000000000")

        self._server = MeterServerService.new_tcp_server(
            ip=ip, port=port, timeout=timeout
        )
        # 确保地址是12位BCD码字符串
        addr_str = str(self._meter_address).zfill(12)
        self._server.set_address(addr_str)

    async def start(self) -> bool:
        """启动 DLT645 服务器"""
        try:
            if self._server and hasattr(self._server, "server"):
                self._server.server.start()
                self._is_running = True
                if self._log:
                    self._log.info(
                        f"DLT645 服务器启动成功, 电表地址: {self._meter_address}"
                    )
                return True
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"启动 DLT645 服务器失败: {e}")
            return False

    async def stop(self) -> bool:
        """停止 DLT645 服务器"""
        try:
            if self._server and hasattr(self._server, "server"):
                self._server.server.stop()
                self._is_running = False
                return True
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"停止 DLT645 服务器失败: {e}")
            return False

    def read_value(self, point: BasePoint) -> Any:
        """读取测点值"""
        if self._server:
            # DLT645 使用数据标识读取，服务端直接返回原始值
            return self._server.get_data(point.address)
        return 0

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值"""
        if self._server:
            # 根据数据标识前缀调用相应的 set_XX 方法
            # address 是 int，转为 hex 字符串查看前缀
            hex_addr = hex(point.address)[2:].zfill(8)
            prefix = hex_addr[:2]
            
            try:
                method_name = f"set_{prefix}"
                if hasattr(self._server, method_name):
                    method = getattr(self._server, method_name)
                    # 服务端模式：直接写入原始映射的值
                    method(point.address, value)
                    return True
                else:
                    # 如果没有对应的前缀方法，尝试通用设置（如果库支持）
                    if self._log:
                        self._log.warning(f"DLT645 服务端暂不支持 DI 前缀 {prefix} (addr: {hex_addr})")
                    return False
            except Exception as e:
                if self._log:
                    self._log.error(f"DLT645 写入数据失败: {e}")
                return False
        return False

    def add_points(self, points: List[BasePoint]) -> None:
        """添加测点（DLT645 按数据标识访问，无需预先添加）"""
        pass

    def get_value_by_address(
        self, func_code: int, slave_id: int, address: int
    ) -> Any:
        """根据地址获取值"""
        if self._server:
            return self._server.get_data(address)
        return 0

    def set_value_by_address(
        self, func_code: int, slave_id: int, address: int, value: Any
    ) -> None:
        """根据地址设置值"""
        if self._server:
            # address 是 int，转为 hex 字符串查看前缀以分发方法
            hex_addr = hex(address)[2:].zfill(8)
            prefix = hex_addr[:2]
            
            try:
                method_name = f"set_{prefix}"
                if hasattr(self._server, method_name):
                    method = getattr(self._server, method_name)
                    method(address, value)
                elif self._log:
                    self._log.warning(f"DLT645 set_value_by_address 暂不支持 DI 前缀 {prefix} (addr: {hex_addr})")
            except Exception as e:
                if self._log:
                    self._log.error(f"DLT645 set_value_by_address 失败: {e}")

    def set_meter_address(self, address: str) -> None:
        """设置电表地址"""
        self._meter_address = address
        if self._server:
            self._server.set_address(address)

    def clear_meter_data(self) -> None:
        """清除电表数据"""
        if self._server and hasattr(self._server, "clear_meter_data"):
            self._server.clear_meter_data()

    @property
    def server(self):
        """获取底层服务器对象"""
        return self._server
