"""
遥测类模块 (Yc - Telemetry)
用于模拟量测量，如电压、电流、功率等
frame_type = 0
"""

from typing import Dict, Optional, Union
from blinker import Signal

from src.enums.points.base_point import BasePoint, decimal_to_hex_formatted
from src.enums.modbus_register import Decode


class Yc(BasePoint):
    """遥测类 - 用于模拟量测量数据"""

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
        mul_coe: float = 1.0,
        add_coe: float = 0,
        frame_type: int = 0,
        decode: str = "0x41",
    ) -> None:
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

        self._max_value_limit: float = float(max_value_limit)
        self._min_value_limit: float = float(min_value_limit)
        self._mul_coe: float = float(mul_coe)
        self._add_coe: float = float(add_coe)
        self._real_value: float = self.value * self.mul_coe + self.add_coe

        # Modbus 解析相关
        self.register_cnt = Decode.get_decode_register_cnt(self.decode)
        self._hex_value = decimal_to_hex_formatted(
            self._value, length=self.register_cnt * 4
        )
        self.is_signed = Decode.is_decode_signed(self.decode)

    def list(self):
        """返回遥测点属性列表"""
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

    # ===== 遥测特有属性 =====

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
        """设置寄存器值，自动计算十六进制和真实值"""
        if not self._is_updating and value != self._value:
            self._is_updating = True
            try:
                self._value = value

                # 根据数据类型选择转换方式
                byteorder = Decode.get_byteorder(self.decode)
                buffer = Decode.pack_value(byteorder, value)

                hex_str = "".join(f"{b:02X}" for b in buffer)
                self._hex_value = f"0x{hex_str}"
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

    def set_real_value(self, real_value) -> bool:
        """通过真实值设置寄存器值"""
        register_value = int((real_value - self.add_coe) / self.mul_coe)
        register_cnt = Decode.get_decode_register_cnt(self.decode)
        is_signed = Decode.is_decode_signed(self.decode)

        # 定义取值范围（无符号/有符号）
        bounds = {
            1: (0, 0xFFFF) if not is_signed else (-0x8000, 0x7FFF),
            2: (0, 0xFFFFFFFF) if not is_signed else (-0x80000000, 0x7FFFFFFF),
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
