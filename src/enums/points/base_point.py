"""
基础测点类模块
提取遥测、遥信、遥调、遥控的公共属性和方法
"""

from typing import Dict, Optional, Union
from blinker import Signal


def decimal_to_hex_formatted(decimal_number: int, length=4) -> str:
    """将十进制数转换为格式化的十六进制字符串"""
    hex_str = hex(decimal_number)[2:].upper().zfill(length)
    return "0x" + hex_str


class BasePoint:
    """测点基类，包含所有测点类型的公共属性和方法"""

    def __init__(
        self,
        rtu_addr: str = "1",
        address: str = "0x0000",
        func_code: int = 3,
        name: str = "",
        code: str = "",
        value: int = 0,
        frame_type: int = 0,
        decode: str = "0x41",
    ) -> None:
        self._is_updating = False
        self._rtu_addr: int = int(rtu_addr)
        self._address: int = int(address, 16)
        self._hex_address: str = str(address)
        self._func_code: int = int(func_code)
        self._name: str = name
        self._code: str = code
        self._value: int = int(value)
        self._hex_value: str = decimal_to_hex_formatted(self._value)
        self._frame_type: int = frame_type
        self._is_simulated: bool = False
        self._is_plan: bool = False
        self.decode = decode

        self.is_send_signal = False
        self.related_point: Optional["BasePoint"] = None
        self.related_value: Dict[int, int] | None = None
        self.value_changed = Signal()
        self.is_signed = False
        self.is_valid = None  # 数据是否有效（None:未知, True:成功, False:失败）

    def list(self) -> list:
        """返回测点属性列表，供表格显示使用"""
        return [
            self.rtu_addr,
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

    # ===== 属性访问器 =====

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
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        """设置测点值，子类可重写以添加特定逻辑"""
        if not self._is_updating and value != self._value:
            self._is_updating = True
            try:
                self._value = value
                if isinstance(value, int):
                    self._hex_value = decimal_to_hex_formatted(value)
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
    def hex_value(self, hex_value):
        self._hex_value = hex_value

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
        """设置真实值，子类需重写此方法"""
        raise NotImplementedError("子类需实现 set_real_value 方法")
