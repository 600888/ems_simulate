from enum import Enum
import struct
from typing import Dict, Optional, Union

from blinker import Signal

from src.enums.modbus_register import Decode, DecodeType


class DeviceType(Enum):
    Pcs = 0
    Bms = 1
    ElectricityMeter = 2
    GridMeter = 3
    CircuitBreaker = 4
    Other = 5


class SimulateMethod(Enum):
    Random = "Random"  # 随机模拟
    AutoIncrement = "AutoIncrement"  # 自增模拟
    AutoDecrement = "AutoDecrement"  # 自减模拟
    Plan = "Plan"  # 计划模拟
    SineWave = "SineWave"  # 正弦波模拟
    Ramp = "Ramp"  # 斜坡模拟
    Pulse = "Pulse"  # 脉冲模拟


def decimal_to_hex_formatted(decimal_number: int, length=4) -> str:
    # 首先转换为十六进制字符串
    hex_str = hex(decimal_number)[2:]  # 去掉'0x'前缀
    # 转换为全大写
    hex_str = hex_str.upper()
    # 确保十六进制字符串至少为length位数（不包括'0x'）
    hex_str = hex_str.zfill(length)  # 使用zfill()方法添加前导零
    # 添加'0x'前缀
    formatted_hex_str = "0x" + hex_str
    return formatted_hex_str


class Yc:
    def __init__(
        self,
        rtu_addr: str = "1",
        address: str = "0x0000",
        func_code: int = 3,
        name: str = "",
        code: str = "",
        value: int = 0,
        max_value_limit: float = 0,
        min_value_limit: float = 0,
        mul_coe: float = 0,
        add_coe: float = 0,
        frame_type: int = 1,
        decode: str = "0x41",
    ) -> None:
        self._is_updating = False
        self._rtu_addr: int = int(rtu_addr)  # RTU地址
        self._address: int = int(address, 16)  # 测点地址
        self._hex_address: str = str(address)  # 测点地址(16进制)
        self._func_code: int = int(func_code)  # 功能码
        self._name: str = name  # 测点名称
        self._code: str = code  # 测点编码
        self._value: int = int(value)  # 测点寄存器值
        self._max_value_limit: float = float(max_value_limit)  # 测点最大值限制
        self._min_value_limit: float = float(min_value_limit)  # 测点最小值限制
        self._mul_coe: float = float(mul_coe)  # 测点值乘积系数
        self._add_coe: float = float(add_coe)  # 测点值加法系数
        self._real_value: float = self.value * self.mul_coe + self.add_coe
        self._frame_type: int = frame_type  # 帧类型
        self._is_simulated: bool = False  # 是否模拟数据
        self._is_plan: bool = False  # 是否计划数据
        self.decode = decode
        self.register_cnt = Decode.get_decode_register_cnt(self.decode)
        self._hex_value: str = decimal_to_hex_formatted(
            self._value, length=self.register_cnt * 4
        )  # 测点值(16进制)
        self.is_signed = Decode.is_decode_signed(self.decode)

        self.is_send_signal = False  # 默认不发出信号
        self.related_point: Optional[Yc] = None
        self.related_value: Dict[int, int] | None = None  # 默认的关联值, 当作int处理
        self.value_changed = Signal()

    def list(self):
        return [
            self.rtu_addr,
            self.hex_address,
            self.func_code,
            self.name,
            self.code,
            self.value,
            self.hex_value,
            self.mul_coe,
            self.add_coe,
            self.frame_type,
            self.is_simulated,
            self.is_plan,
        ]

    @property
    def rtu_addr(self) -> int:
        return self._rtu_addr

    @rtu_addr.setter
    def rtu_addr(self, rtu_addr):
        self._rtu_addr = rtu_addr

    @property
    def address(self) -> int:
        return self._address

    @address.setter
    def address(self, address):
        self._address = address
        self.hex_address = decimal_to_hex_formatted(address)

    @property
    def hex_address(self) -> str:
        return self._hex_address

    @hex_address.setter
    def hex_address(self, hex_address):
        self._hex_address = hex_address

    @property
    def func_code(self) -> int:
        return self._func_code

    @func_code.setter
    def func_code(self, func_code):
        self._func_code = func_code

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    @property
    def code(self) -> str:
        return self._code

    @code.setter
    def code(self, code):
        self._code = code

    @property
    def max_value_limit(self) -> float:
        return self._max_value_limit

    @max_value_limit.setter
    def max_value_limit(self, max_value_limit):
        self._max_value_limit = max_value_limit

    @property
    def min_value_limit(self) -> float:
        return self._min_value_limit

    @min_value_limit.setter
    def min_value_limit(self, min_value_limit):
        self._min_value_limit = min_value_limit

    @property
    def hex_value(self) -> str:
        return self._hex_value

    @hex_value.setter
    def hex_value(self, hex_value):
        self._hex_value = hex_value

    @property
    def mul_coe(self) -> float:
        return self._mul_coe

    @mul_coe.setter
    def mul_coe(self, mul_coe):
        self._mul_coe = mul_coe

    @property
    def add_coe(self) -> float:
        return self._add_coe

    @add_coe.setter
    def add_coe(self, add_coe: int):
        self._add_coe = add_coe

    @property
    def value(self) -> int:
        return self._value

    @value.setter
    def value(self, value: Union[int, float]):
        if not self._is_updating and value != self._value:
            self._is_updating = True
            try:
                self._value = value

                # 根据数据类型选择转换方式
                byteorder = Decode.get_byteorder(self.decode)
                buffer = Decode.pack_value(byteorder, value)

                hex_str = "".join(f"{b:02X}" for b in buffer)
                self._hex_value = f"0x{hex_str}"
                # self._real_value = float((value - int(self._add_coe)) * self._mul_coe)
                self.real_value = value * self._mul_coe + self._add_coe
                if self.is_send_signal:
                    self.value_changed.send(
                        old_point=self, related_point=self.related_point
                    )
            finally:
                self._is_updating = False

    @property
    def real_value(self) -> float:
        return self._real_value

    @real_value.setter
    def real_value(self, real_value):
        self._real_value = real_value

    @property
    def frame_type(self) -> int:
        return self._frame_type

    @frame_type.setter
    def frame_type(self, frame_type):
        self._frame_type = frame_type

    @property
    def is_simulated(self) -> bool:
        return self._is_simulated

    @is_simulated.setter
    def is_simulated(self, is_simulated):
        self._is_simulated = is_simulated

    @property
    def is_plan(self) -> bool:
        return self._is_plan

    @is_plan.setter
    def is_plan(self, is_plan):
        self._is_plan = is_plan

    def set_real_value(self, real_value) -> bool:
        register_value = int((real_value - self.add_coe) / self.mul_coe)
        register_cnt = Decode.get_decode_register_cnt(self.decode)
        is_signed = Decode.is_decode_signed(self.decode)  # 判断解析码是否支持负数

        # 定义取值范围（无符号/有符号）
        bounds = {
            1: (0, 0xFFFF) if not is_signed else (-0x8000, 0x7FFF),  # 16位
            2: (0, 0xFFFFFFFF) if not is_signed else (-0x80000000, 0x7FFFFFFF),  # 32位
        }

        if register_cnt not in bounds:
            return False

        min_val, max_val = bounds[register_cnt]
        if min_val <= register_value <= max_val:
            self.real_value = real_value
            self.value = register_value
            return True
        else:
            return False


class Yx:
    def __init__(
        self,
        rtu_addr: str = "0",
        address: str = "0x0000",
        bit: str = "0",
        func_code: int = 3,
        name: str = "",
        code: str = "",
        value: int = 0,
        frame_type: int = 1,
        decode: str = "0x20",
    ):
        self._is_updating = False
        self._rtu_addr: int = int(rtu_addr)  # RTU地址
        self._address: int = int(address, 16)  # 测点地址
        self._bit: int = int(bit)  # 测点位
        self._hex_address: str = address  # 测点地址(16进制)
        self._func_code: int = int(func_code)  # 功能码
        self._name: str = name  # 测点名称
        self._code: str = code  # 测点编码
        self._value: int = value  # 测点值
        self._hex_value: str = decimal_to_hex_formatted(self._value)  # 测点值(16进制)
        self._frame_type: int = frame_type  # 帧类型
        self._is_simulated: bool = False  # 是否模拟数据
        self._is_plan: bool = False  # 是否计划数据
        self.decode = decode

        self.is_send_signal = False  # 默认不发出信号
        self.related_point: Optional[Yx] = None
        self.related_value: Dict[int, int] | None = None
        self.value_changed = Signal()
        self.is_signed = False

    def list(self):
        return [
            self.rtu_addr,
            self.address,
            self.bit,
            self.hex_address,
            self.func_code,
            self.name,
            self.code,
            self.value,
            self.hex_value,
            self.frame_type,
            self.is_simulated,
            self.is_plan,
        ]

    @property
    def rtu_addr(self) -> int:
        return self._rtu_addr

    @rtu_addr.setter
    def rtu_addr(self, rtu_addr: int):
        self._rtu_addr = rtu_addr

    @property
    def address(self) -> int:
        return self._address

    @address.setter
    def address(self, address: int):
        self._address = address
        self.hex_address = decimal_to_hex_formatted(address)

    @property
    def bit(self) -> int:
        return self._bit

    @bit.setter
    def bit(self, bit: int):
        self._bit = bit

    @property
    def hex_address(self) -> str:
        return self._hex_address

    @hex_address.setter
    def hex_address(self, hex_address):
        self._hex_address = hex_address

    @property
    def func_code(self) -> int:
        return self._func_code

    @func_code.setter
    def func_code(self, func_code: int):
        self._func_code = func_code

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, name: str):
        self._name = name

    @property
    def code(self) -> str:
        return self._code

    @code.setter
    def code(self, code: str):
        self._code = code

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        if not self._is_updating and value != self._value:
            self._is_updating = True
            try:
                self._value = value
                if isinstance(self.value, int):
                    self.hex_value = decimal_to_hex_formatted(value)
                if self.is_send_signal:
                    self.value_changed.send(
                        old_point=self, related_point=self.related_point
                    )
            finally:
                self._is_updating = False

    @property
    def hex_value(self) -> str:
        return self._hex_value

    @hex_value.setter
    def hex_value(self, hex_value: str):
        self._hex_value = hex_value

    @property
    def frame_type(self) -> int:
        return self._frame_type

    @frame_type.setter
    def frame_type(self, frame_type: int):
        self._frame_type = frame_type

    @property
    def is_simulated(self) -> bool:
        return self._is_simulated

    @is_simulated.setter
    def is_simulated(self, is_simulated: bool):
        self._is_simulated = is_simulated

    @property
    def is_plan(self) -> bool:
        return self._is_plan

    @is_plan.setter
    def is_plan(self, is_plan: bool):
        self._is_plan = is_plan

    def set_real_value(self, real_value) -> bool:
        if 0 <= int(real_value) <= 1:
            self.real_value = int(real_value)
            self.value = int(real_value)
            return True
        else:
            return False
