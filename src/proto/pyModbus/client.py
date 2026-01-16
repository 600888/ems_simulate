import struct
from typing import List, Optional, Union
from pymodbus.client import ModbusTcpClient, ModbusSerialClient
from pymodbus.exceptions import ModbusException
from src.enums.modbus_register import Decode, DecodeType
from src.enums.modbus_def import ProtocolType


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
            if self.protocol_type in [
                ProtocolType.ModbusTcp,
                ProtocolType.ModbusRtuOverTcp,
            ]:
                self.client = ModbusTcpClient(host=self.host, port=self.port)
            elif self.protocol_type == ProtocolType.ModbusRtu:
                self.client = ModbusSerialClient(
                    port=self.serial_port,
                    baudrate=self.baudrate,
                    bytesize=self.bytesize,
                    parity=self.parity,
                    stopbits=self.stopbits,
                )
            else:
                if self.log:
                    self.log.error(f"Unsupported protocol type: {self.protocol_type}")
                else:
                    print(f"Unsupported protocol type: {self.protocol_type}")

            self.connected = self.client.connect()
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

        try:
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
        decode: str = "0x20",
        register_cnt: int = 1,
        signed: bool = False,
    ) -> Union[int, float]:
        """
        根据解析码读取寄存器值并解析为指定数据类型

        Args:
            func_code: 功能码
            slave_id: 从站地址
            address: 寄存器地址
            decode: 解析码
            register_count: 寄存器数量
            signed: 是否为有符号数

        Returns:
            Union[int, float]: 解析后的值
        """
        if not self.connected:
            self.connect()

        # 读取寄存器值
        if func_code == 1:  # 读取线圈
            values = self.read_coils(slave_id, address, register_cnt)
            return values[0] if values else 0
        elif func_code == 2:  # 读取离散输入
            values = self.read_discrete_inputs(slave_id, address, register_cnt)
            return values[0] if values else 0
        elif func_code == 3:  # 读取保持寄存器
            registers = self.read_holding_registers(slave_id, address, register_cnt)
        elif func_code == 4:  # 读取输入寄存器
            registers = self.read_input_registers(slave_id, address, register_cnt)
        else:
            log.error(f"Unsupported function code: {func_code}")

        if not registers:
            return 0

        # 根据解析码处理数据类型
        endian = Decode.get_endian(decode)

        if register_cnt == 2:  # 32位数据
            packed = struct.pack(f"{endian}HH", *registers)
            if Decode.get_decode_type(decode) == DecodeType.Float:
                return struct.unpack(f"{endian}f", packed)[0]
            else:
                fmt = f"{endian}l" if signed else f"{endian}L"
                return struct.unpack(fmt, packed)[0]
        else:  # 16位数据
            value = registers[0]
            # 小端序处理
            if endian == "<":
                value = ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)
            # 有符号数处理
            if signed and value > 0x7FFF:
                value -= 0x10000
            return value

    def write_value_by_address(
        self,
        func_code: int,
        slave_id: int,
        address: int,
        value: Union[int, float],
        decode: str = "0x20",
        register_cnt: int = 1,
        signed: bool = False,
    ) -> bool:
        """
        根据解析码将值写入寄存器

        Args:
            func_code: 功能码
            slave_id: 从站地址
            address: 寄存器地址
            value: 要写入的值
            decode: 解析码
            register_count: 寄存器数量
            signed: 是否为有符号数

        Returns:
            bool: 写入是否成功
        """
        if not self.connected:
            self.connect()

        # 根据解析码准备要写入的寄存器值
        decode_type = Decode.get_decode_type(decode)
        endian = Decode.get_endian(decode)

        if register_cnt == 2:
            if decode_type == DecodeType.Float:  # 浮点数处理
                packed = struct.pack(f"{endian}f", float(value))
                registers = list(struct.unpack(f"{endian}HH", packed))
            else:
                fmt = f"{endian}l" if signed else f"{endian}L"
                packed = struct.pack(fmt, int(value))
                registers = list(struct.unpack(f"{endian}HH", packed))
        elif register_cnt == 1:  # 默认16位整数
            val = int(value)
            if signed and val < 0:
                val = (1 << 16) + val
            registers = [val & 0xFFFF]
            # 小端序处理
            if endian == "<":
                registers[0] = ((registers[0] & 0xFF) << 8) | (
                    (registers[0] >> 8) & 0xFF
                )

        # 写入寄存器值
        if func_code in [5, 15]:  # 线圈操作
            return self.write_multiple_coils(
                slave_id, address, [bool(v) for v in registers]
            )
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
