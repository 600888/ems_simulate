"""
遥信类模块 (Yx - Telesignaling)
用于状态信号，如开关状态、告警信号等
frame_type = 1
"""

from typing import Dict, Optional
from blinker import Signal

from src.enums.points.base_point import BasePoint, decimal_to_hex_formatted


class Yx(BasePoint):
    """遥信类 - 用于状态信号数据"""

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
        super().__init__(
            rtu_addr=rtu_addr,
            address=address,
            func_code=func_code,
            name=name,
            code=code,
            value=value,
            frame_type=frame_type,
            decode=decode,
        )

        self._bit: int = int(bit)
        self._hex_value: str = decimal_to_hex_formatted(self._value)

    def list(self):
        """返回遥信点属性列表"""
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

    # ===== 遥信特有属性 =====

    @property
    def bit(self) -> int:
        return self._bit

    @bit.setter
    def bit(self, bit: int):
        self._bit = bit

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        """设置遥信值"""
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

    def set_real_value(self, real_value) -> bool:
        """设置遥信真实值（仅允许 0 或 1）"""
        if 0 <= int(real_value) <= 1:
            self.real_value = int(real_value)
            self.value = int(real_value)
            return True
        else:
            return False

    @property
    def real_value(self):
        """遥信的真实值就是其值本身"""
        return self._value

    @real_value.setter
    def real_value(self, value):
        self._value = value
