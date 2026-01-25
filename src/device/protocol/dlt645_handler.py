"""
DLT645 协议处理器
支持 DLT645 电力表计协议服务端和客户端
"""

from typing import Any, Dict, List, Optional

from src.device.protocol.base_handler import ServerHandler, ClientHandler
from src.enums.point_data import Yc
from src.config.config import Config
from src.enums.points.base_point import BasePoint


class DLT645ServerHandler(ServerHandler):
    """DLT645 服务端处理器
    
    支持 TCP 和 RTU（串口）两种连接方式。
    """

    def __init__(self, log=None):
        super().__init__()
        self._server = None
        self._log = log
        self._meter_address: str = "000000000000"
        self._is_serial: bool = False  # 是否为串口模式

    def initialize(self, config: Dict[str, Any]) -> None:
        """初始化 DLT645 服务器
        
        Args:
            config: 配置字典，包含:
                TCP 模式:
                    - ip: 监听 IP（默认 0.0.0.0）
                    - port: 监听端口（默认 8899）
                RTU（串口）模式:
                    - serial_port: 串口号（如 COM1 或 /dev/ttyUSB0）
                    - baudrate: 波特率（默认 9600）
                    - databits: 数据位（默认 8）
                    - stopbits: 停止位（默认 1）
                    - parity: 校验位（默认 "E" 偶校验）
                通用:
                    - meter_address: 电表地址（12位BCD码）
                    - timeout: 超时时间（默认 30）
        """
        from dlt645.service.serversvc.server_service import MeterServerService

        self._config = config
        timeout = config.get("timeout", 30)
        self._meter_address = config.get("meter_address", "000000000000")
        
        # 判断使用 TCP 还是 RTU 模式
        serial_port = config.get("serial_port")
        
        if serial_port:
            # RTU（串口）模式
            self._is_serial = True
            baudrate = config.get("baudrate", 9600)
            databits = config.get("databits", 8)
            stopbits = config.get("stopbits", 1)
            parity = config.get("parity", "E")
            
            self._server = MeterServerService.new_rtu_server(
                port=serial_port,
                data_bits=databits,
                stop_bits=stopbits,
                baud_rate=baudrate,
                parity=parity,
                timeout=timeout
            )
        else:
            # TCP 模式
            self._is_serial = False
            ip = config.get("ip", "0.0.0.0")
            port = config.get("port", 8899)
            
            self._server = MeterServerService.new_tcp_server(
                ip=ip, port=port, timeout=timeout
            )
        
        # 确保地址是12位BCD码字符串
        addr_str = str(self._meter_address).zfill(12)
        self._server.set_address(addr_str)
        
        # 启用报文捕获
        self._server.enable_message_capture(queue_size=200)

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
    
    def get_captured_messages(self, count: int = 100) -> list:
        """获取捕获的报文列表
        
        Returns:
            报文记录列表，每条记录包含 direction, hex_string, timestamp 等
        """
        if self._server and hasattr(self._server, 'get_captured_messages'):
            messages = self._server.get_captured_messages(count)
            return [msg.to_dict() for msg in messages]
        return []
    
    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        if self._server and hasattr(self._server, 'clear_captured_messages'):
            self._server.clear_captured_messages()


class DLT645ClientHandler(ClientHandler):
    """DLT645 客户端处理器
    
    作为主站（客户端）连接到远程电表，主动读取电表数据。
    支持 TCP 和 RTU（串口）两种连接方式。
    """

    def __init__(self, log=None):
        super().__init__()
        self._client = None  # MeterClientService 实例
        self._transport_client = None  # TcpClient 或 RtuClient 底层连接
        self._log = log
        self._meter_address: str = "000000000000"
        self._is_serial: bool = False  # 是否为串口模式

    def initialize(self, config: Dict[str, Any]) -> None:
        """初始化 DLT645 客户端
        
        Args:
            config: 配置字典，包含:
                TCP 模式:
                    - ip: 服务器 IP
                    - port: 服务器端口（默认 8899）
                RTU（串口）模式:
                    - serial_port: 串口号（如 COM1 或 /dev/ttyUSB0）
                    - baudrate: 波特率（默认 9600）
                    - databits: 数据位（默认 8）
                    - stopbits: 停止位（默认 1）
                    - parity: 校验位（默认 "E" 偶校验）
                通用:
                    - meter_address: 电表地址（12位BCD码）
                    - timeout: 超时时间（默认 30）
        """
        from dlt645.service.clientsvc.client_service import MeterClientService

        self._config = config
        timeout = config.get("timeout", 3)  # 默认3秒超时，避免长时间阻塞
        self._meter_address = config.get("meter_address", "000000000000")
        
        # 判断使用 TCP 还是 RTU 模式
        serial_port = config.get("serial_port")
        
        if serial_port:
            # RTU（串口）模式
            self._is_serial = True
            baudrate = config.get("baudrate", 9600)
            databits = config.get("databits", 8)
            stopbits = config.get("stopbits", 1)
            parity = config.get("parity", "E")
            
            self._client = MeterClientService.new_rtu_client(
                port=serial_port,
                baudrate=baudrate,
                databits=databits,
                stopbits=stopbits,
                parity=parity,
                timeout=timeout
            )
        else:
            # TCP 模式
            self._is_serial = False
            ip = config.get("ip", "127.0.0.1")
            port = config.get("port", Config.DLT645_DEFAULT_PORT)
            
            self._client = MeterClientService.new_tcp_client(
                ip=ip, port=port, timeout=timeout
            )
        
        if self._client:
            # 设置电表地址（12位BCD码字符串）
            addr_str = str(self._meter_address).zfill(12)
            self._client.set_address(addr_str)
            # 保存底层传输客户端引用
            self._transport_client = self._client.client

    async def start(self) -> bool:
        """启动客户端（非阻塞，在线程池中连接）"""
        import asyncio
        loop = asyncio.get_event_loop()
        # 在线程池中执行阻塞的连接操作，避免阻塞事件循环
        return await loop.run_in_executor(None, self.connect)

    async def stop(self) -> bool:
        """停止客户端（断开连接）"""
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.disconnect)
        return True

    def connect(self) -> bool:
        """连接到 DLT645 电表"""
        try:
            if self._transport_client:
                result = self._transport_client.connect()
                if result:
                    self._is_running = True
                    mode = "串口" if self._is_serial else "TCP"
                    if self._log:
                        self._log.info(
                            f"DLT645 客户端({mode})连接成功, 电表地址: {self._meter_address}"
                        )
                return result
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"连接 DLT645 电表失败: {e}")
            return False

    def disconnect(self) -> None:
        """断开连接"""
        if self._transport_client:
            try:
                self._transport_client.disconnect()
            except Exception:
                pass
            self._is_running = False

    def read_value(self, point: BasePoint) -> Any:
        """读取测点值
        
        从远程电表读取数据标识对应的值。
        根据 DI 前缀调用相应的 read_XX 方法。
        """
        if not self._client:
            return 0
            
        try:
            # DLT645 使用数据标识 (DI) 读取
            di = point.address
            hex_addr = hex(di)[2:].zfill(8)
            prefix = hex_addr[:2]  # DI 前缀决定读取方法
            
            # 根据 DI 前缀选择读取方法
            data_item = None
            if prefix == "00":
                data_item = self._client.read_00(di)  # 读取电能
            elif prefix == "01":
                data_item = self._client.read_01(di)  # 读取最大需量
            elif prefix == "02":
                data_item = self._client.read_02(di)  # 读取变量
            elif prefix == "03":
                data_item = self._client.read_03(di)  # 读取事件记录
            elif prefix == "04":
                data_item = self._client.read_04(di)  # 读取参变量
            else:
                if self._log:
                    self._log.warning(f"DLT645 客户端暂不支持 DI 前缀 {prefix} (addr: {hex_addr})")
                return 0
            
            if data_item is None:
                return 0
            
            # 从 DataItem 获取值
            real_val = data_item.value if hasattr(data_item, 'value') else 0
            if real_val is None:
                return 0
            
            # 如果是遥测点，需要根据系数反向换算回原始值
            if isinstance(point, Yc):
                try:
                    return int((float(real_val) - point.add_coe) / point.mul_coe)
                except (ZeroDivisionError, TypeError, ValueError):
                    return 0
            return real_val
            
        except Exception as e:
            if self._log:
                self._log.error(f"DLT645 读取数据失败: {e}")
            return 0

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值（发送命令）
        
        向远程电表写入数据。注意：大多数电表数据是只读的，
        只有 DI 前缀为 04 的参变量支持写入。
        """
        if not self._client:
            return False
            
        try:
            di = point.address
            hex_addr = hex(di)[2:].zfill(8)
            prefix = hex_addr[:2]
            
            # 只有参变量 (04) 支持写入
            if prefix == "04":
                # 客户端写入：将内部原始值换算为物理值发送
                real_to_send = value
                if isinstance(point, Yc):
                    real_to_send = value * point.mul_coe + point.add_coe
                
                # 写参变量需要密码，这里使用默认空密码
                result = self._client.write_04(di, str(real_to_send), "00000000")
                return result is not None
            else:
                if self._log:
                    self._log.warning(f"DLT645 客户端只能写入参变量 (DI前缀04), 当前: {prefix}")
                return False
                
        except Exception as e:
            if self._log:
                self._log.error(f"DLT645 写入数据失败: {e}")
            return False

    def add_points(self, points: List[BasePoint]) -> None:
        """添加测点（DLT645 客户端按需读写，无需预先添加）"""
        pass

    def set_meter_address(self, address: str) -> None:
        """设置电表地址"""
        self._meter_address = address
        if self._client:
            self._client.set_address(address)

    @property
    def client(self):
        """获取底层客户端对象"""
        return self._client
    
    def get_captured_messages(self, count: int = 100) -> list:
        """获取捕获的报文列表
        
        Returns:
            报文记录列表，每条记录包含 direction, hex_string, timestamp 等
        """
        if self._client and hasattr(self._client, 'get_captured_messages'):
            messages = self._client.get_captured_messages(count)
            return [msg.to_dict() for msg in messages]
        return []
    
    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        if self._client and hasattr(self._client, 'clear_captured_messages'):
            self._client.clear_captured_messages()
