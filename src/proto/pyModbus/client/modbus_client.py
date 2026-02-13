import struct
from typing import List, Optional, Union
from pymodbus.client import ModbusTcpClient, ModbusSerialClient
from pymodbus.exceptions import ModbusException
from src.enums.modbus_register import Decode, DecodeType
from pymodbus.framer import Framer
from pymodbus.pdu import ModbusRequest
from datetime import datetime
from src.enums.modbus_def import ProtocolType
from src.device.core.message.message_capture import MessageCapture

# 从子模块导入捕获客户端
from .capture import (
    ModbusTcpClientWithCapture,
    ModbusSerialClientWithCapture,
    ModbusRtuOverTcpClientWithCapture
)

class ModbusClient:
    """
    Modbus客户端类，用于连接和操作Modbus服务器
    支持TCP和串行连接
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 502,
        protocol_type: ProtocolType = ProtocolType.ModbusTcp,
        serial_port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: int = 1,
        log=None,
    ):
        """
        初始化Modbus客户端

        Args:
            host: 主机地址
            port: 端口号
            protocol_type: 协议类型
            serial_port: 串口端口
            baudrate: 波特率
            bytesize: 数据位
            parity: 校验位
            stopbits: 停止位
        """
        self.host = host
        self.port = port
        self.protocol_type = protocol_type
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.client = None
        self.connected = False
        self.log = log
        self.message_capture = MessageCapture() # 报文捕获器

    def getCapturedMessages(self, limit: int = 100):
        """获取捕获的报文"""
        return self.message_capture.get_messages(limit)

    def clearCapturedMessages(self):
        """清空捕获的报文"""
        self.message_capture.clear()

    def is_connected(self) -> bool:
        """
        检查是否已连接到Modbus服务器

        Returns:
            bool: 是否已连接
        """
        return self.connected

    def connect(self) -> bool:
        """
        连接到Modbus服务器

        Returns:
            bool: 连接是否成功
        """
        try:
            if self.protocol_type == ProtocolType.ModbusTcp or self.protocol_type == ProtocolType.ModbusTcpClient:
                self.client = ModbusTcpClientWithCapture(
                    host=self.host, 
                    port=self.port, 
                    message_capture=self.message_capture,
                    timeout=1.0,  # 减少超时时间，避免长时间阻塞
                    retries=1     # 减少重试次数
                )
            elif self.protocol_type == ProtocolType.ModbusRtuOverTcp:
                self.client = ModbusRtuOverTcpClientWithCapture(
                    host=self.host, 
                    port=self.port, 
                    message_capture=self.message_capture,
                    timeout=1.0,
                    retries=1
                )
            elif self.protocol_type == ProtocolType.ModbusRtu:
                self.client = ModbusSerialClientWithCapture(
                    port=self.serial_port,
                    baudrate=self.baudrate,
                    bytesize=self.bytesize,
                    parity=self.parity,
                    stopbits=self.stopbits,
                    message_capture=self.message_capture
                )
            else:
                if self.log:
                    self.log.error(f"Unsupported protocol type: {self.protocol_type}")
                else:
                    print(f"Unsupported protocol type: {self.protocol_type}")

            self.connected = self.client.connect()
            
            # 双重检查：确认 socket 是否真正建立
            if self.connected:
                if self.log:
                    self.log.info(f"Modbus 客户端已连接到 {self.host}:{self.port}")
                # 某些版本的 pymodbus 可能在连接失败时仍返回 True (因为启用了重试机制)
                # 这里强制检查 socket 对象是否创建
                socket_obj = getattr(self.client, 'socket', None)
                if socket_obj is None:
                    if self.log:
                        self.log.error("Modbus client connect() returned True but socket is None")
                    self.connected = False
            else:
                if self.log:
                    self.log.error(f"Modbus 客户端连接失败: {self.host}:{self.port}")
            return self.connected
        except Exception as e:
            if self.log:
                self.log.error(f"Failed to connect to Modbus server: {e}")
            else:
                print(f"Failed to connect to Modbus server: {e}")
            self.connected = False
            return False

    def disconnect(self) -> None:
        """
        断开与Modbus服务器的连接
        """
        if self.client:
            self.client.close()
        self.connected = False

    def read_coils(self, slave_id: int, address: int, count: int = 1) -> List[bool]:
        """
        读取线圈状态 (功能码 0x01)

        Args:
            slave_id: 从站地址
            address: 起始地址
            count: 读取数量

        Returns:
            List[bool]: 线圈状态列表
        """
        if not self.connected:
            raise ConnectionError("Client not connected to server")

        try:
            response = self.client.read_coils(address, count, slave=slave_id)
            if not response.isError():
                return response.bits[:count]
            else:
                if self.log:
                    self.log.error(f"Error reading coils: {response}")
                else:
                    print(f"Error reading coils: {response}")
                return []
        except ModbusException as e:
            if self.log:
                self.log.error(f"Modbus error reading coils: {e}")
            else:
                print(f"Modbus error reading coils: {e}")
            return []

    def read_discrete_inputs(
        self, slave_id: int, address: int, count: int = 1
    ) -> List[bool]:
        """
        读取离散输入 (功能码 0x02)

        Args:
            slave_id: 从站地址
            address: 起始地址
            count: 读取数量

        Returns:
            List[bool]: 离散输入状态列表
        """
        if not self.connected:
            raise ConnectionError("Client not connected to server")

        try:
            response = self.client.read_discrete_inputs(address, count, slave=slave_id)
            if not response.isError():
                return response.bits[:count]
            else:
                if self.log:
                    self.log.error(f"Error reading discrete inputs: {response}")
                else:
                    print(f"Error reading discrete inputs: {response}")
                return []
        except ModbusException as e:
            if self.log:
                self.log.error(f"Modbus error reading discrete inputs: {e}")
            else:
                print(f"Modbus error reading discrete inputs: {e}")
            return []

    def read_holding_registers(
        self, slave_id: int, address: int, count: int = 1
    ) -> List[int]:
        """
        读取保持寄存器 (功能码 0x03)

        Args:
            slave_id: 从站地址
            address: 起始地址
            count: 读取数量

        Returns:
            List[int]: 寄存器值列表
        """
        if not self.connected:
            if self.log:
                self.log.error("Client not connected to server")
            else:
                print("Client not connected to server")
            return []  # 未连接时直接返回空列表

        try:
            # 调试日志
            if self.log:
                self.log.debug(f"读取保持寄存器: slave={slave_id}, addr={address}, count={count}")
            
            response = self.client.read_holding_registers(
                address, count, slave=slave_id
            )
            if not response.isError():
                return response.registers
            else:
                if self.log:
                    self.log.error(f"Error reading holding registers: {response}")
                else:
                    print(f"Error reading holding registers: {response}")
                return []
        except ModbusException as e:
            if self.log:
                self.log.error(f"Modbus error reading holding registers: {e}")
            else:
                print(f"Modbus error reading holding registers: {e}")
            return []

    def read_input_registers(
        self, slave_id: int, address: int, count: int = 1
    ) -> List[int]:
        """
        读取输入寄存器 (功能码 0x04)

        Args:
            slave_id: 从站地址
            address: 起始地址
            count: 读取数量

        Returns:
            List[int]: 寄存器值列表
        """
        if not self.connected:
            if self.log:
                self.log.error("Client not connected to server")
            else:
                print("Client not connected to server")

        try:
            response = self.client.read_input_registers(address, count, slave=slave_id)
            if not response.isError():
                return response.registers
            else:
                if self.log:
                    self.log.error(f"Error reading input registers: {response}")
                else:
                    print(f"Error reading input registers: {response}")
                return []
        except ModbusException as e:
            if self.log:
                self.log.error(f"Modbus error reading input registers: {e}")
            else:
                print(f"Modbus error reading input registers: {e}")
            return []

    def write_single_coil(self, slave_id: int, address: int, value: bool) -> bool:
        """
        写入单个线圈 (功能码 0x05)

        Args:
            slave_id: 从站地址
            address: 线圈地址
            value: 线圈值 (True/False)

        Returns:
            bool: 写入是否成功
        """
        if not self.connected:
            if self.log:
                self.log.error("Client not connected to server")
            else:
                print("Client not connected to server")

        try:
            response = self.client.write_coil(address, value, slave=slave_id)
            return not response.isError()
        except ModbusException as e:
            if self.log:
                self.log.error(f"Modbus error writing single coil: {e}")
            else:
                print(f"Modbus error writing single coil: {e}")
            return False

    def write_single_register(self, slave_id: int, address: int, value: int) -> bool:
        """
        写入单个保持寄存器 (功能码 0x06)

        Args:
            slave_id: 从站地址
            address: 寄存器地址
            value: 寄存器值

        Returns:
            bool: 写入是否成功
        """
        if not self.connected:
            if self.log:
                self.log.error("Client not connected to server")
            else:
                print("Client not connected to server")

        try:
            response = self.client.write_register(address, value, slave=slave_id)
            return not response.isError()
        except ModbusException as e:
            if self.log:
                self.log.error(f"Modbus error writing single register: {e}")
            else:
                print(f"Modbus error writing single register: {e}")
            return False

    def write_multiple_coils(
        self, slave_id: int, address: int, values: List[bool]
    ) -> bool:
        """
        写入多个线圈 (功能码 0x0F)

        Args:
            slave_id: 从站地址
            address: 起始地址
            values: 线圈值列表

        Returns:
            bool: 写入是否成功
        """
        if not self.connected:
            if self.log:
                self.log.error("Client not connected to server")
            else:
                print("Client not connected to server")

        try:
            response = self.client.write_coils(address, values, slave=slave_id)
            return not response.isError()
        except ModbusException as e:
            if self.log:
                self.log.error(f"Modbus error writing multiple coils: {e}")
            else:
                print(f"Modbus error writing multiple coils: {e}")
            return False

    def write_multiple_registers(
        self, slave_id: int, address: int, values: List[int]
    ) -> bool:
        """
        写入多个保持寄存器 (功能码 0x10)

        Args:
            slave_id: 从站地址
            address: 起始地址
            values: 寄存器值列表

        Returns:
            bool: 写入是否成功
        """
        if not self.connected:
            if self.log:
                self.log.error("Client not connected to server")
            else:
                print("Client not connected to server")

        try:
            response = self.client.write_registers(address, values, slave=slave_id)
            return not response.isError()
        except ModbusException as e:
            if self.log:
                self.log.error(f"Modbus error writing multiple registers: {e}")
            else:
                print(f"Modbus error writing multiple registers: {e}")
            return False

    def read_value_by_address(
        self,
        func_code: int,
        slave_id: int,
        address: int,
        decode: str = "0x41",
    ) -> Optional[Union[int, float]]:
        """
        根据解析码读取寄存器值并解析为指定数据类型
        使用 DecodeInfo 统一配置处理

        Args:
            func_code: 功能码
            slave_id: 从站地址
            address: 寄存器地址
            decode: 解析码

        Returns:
            Optional[Union[int, float]]: 解析后的值, 读取失败返回 None
        """
        if not self.connected:
            return None

        # 获取解析码完整信息
        info = Decode.get_info(decode)
        register_cnt = info.register_cnt

        values = None
        registers = None

        # 读取寄存器值
        # 读取寄存器值
        if func_code == 1 or func_code == 5 or func_code == 15:  # 读取线圈
            values = self.read_coils(slave_id, address, register_cnt)
            if not values:
                return None
            return values[0]
        elif func_code == 2:  # 读取离散输入
            values = self.read_discrete_inputs(slave_id, address, register_cnt)
            if not values:
                return None
            return values[0]
        elif func_code == 3 or func_code == 6 or func_code == 16:  # 读取保持寄存器
            registers = self.read_holding_registers(slave_id, address, register_cnt)
        elif func_code == 4:  # 读取输入寄存器
            registers = self.read_input_registers(slave_id, address, register_cnt)
        else:
            if self.log:
                self.log.error(f"Unsupported function code: {func_code}")
            return None

        if not registers:
            return None

        # 将寄存器值打包为字节
        if register_cnt == 4:  # 64位
            packed = struct.pack(">HHHH" if info.is_big_endian else "<HHHH", *registers)
        elif register_cnt == 2:  # 32位
            packed = struct.pack(">HH" if info.is_big_endian else "<HH", *registers)
        else:  # 16位
            value = registers[0]
            if not info.is_big_endian:  # 小端序处理
                value = ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)
            if info.is_signed and value > 0x7FFF:
                value -= 0x10000
            return value
        
        # 使用统一的解包方法
        return Decode.unpack_value(info.pack_format, packed)

    def write_value_by_address(
        self,
        func_code: int,
        slave_id: int,
        address: int,
        value: Union[int, float],
        decode: str = "0x41",
    ) -> bool:
        """
        根据解析码将值写入寄存器
        使用 DecodeInfo 统一配置处理

        Args:
            func_code: 功能码
            slave_id: 从站地址
            address: 寄存器地址
            value: 要写入的值
            decode: 解析码

        Returns:
            bool: 写入是否成功
        """
        if not self.connected:
            return False

        # 获取解析码完整信息
        info = Decode.get_info(decode)
        register_cnt = info.register_cnt
        
        # 使用统一的打包方法
        packed = Decode.pack_value(info.pack_format, value)
        
        # 将打包后的字节转换为寄存器值列表
        if register_cnt == 4:  # 64位
            registers = list(struct.unpack(">HHHH" if info.is_big_endian else "<HHHH", packed))
        elif register_cnt == 2:  # 32位
            registers = list(struct.unpack(">HH" if info.is_big_endian else "<HH", packed))
        else:  # 16位
            val = int(value)
            if info.is_signed and val < 0:
                val = (1 << 16) + val
            registers = [val & 0xFFFF]
            if not info.is_big_endian:  # 小端序处理
                registers[0] = ((registers[0] & 0xFF) << 8) | ((registers[0] >> 8) & 0xFF)

        # 写入寄存器值
        if func_code in [5, 15]:  # 线圈操作
            return self.write_multiple_coils(slave_id, address, [bool(v) for v in registers])
        elif func_code in [6, 16]:  # 寄存器操作
            if func_code == 6 and len(registers) == 1:
                return self.write_single_register(slave_id, address, registers[0])
            else:
                return self.write_multiple_registers(slave_id, address, registers)
        else:
            if self.log:
                self.log.error(f"Unsupported function code for writing: {func_code}")
            else:
                print(f"Unsupported function code for writing: {func_code}")
            return False
