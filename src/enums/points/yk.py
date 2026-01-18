"""
遥控类模块 (Yk - Telecontrol)
用于远程控制命令，如开关控制、启停命令等
frame_type = 2
"""

from typing import Dict, Optional
from blinker import Signal

from src.enums.points.base_point import BasePoint, decimal_to_hex_formatted


class Yk(BasePoint):
    """遥控类 - 用于远程控制命令"""

    def __init__(
        self,
        rtu_addr: str = "1",
        address: str = "0x0000",
        bit: str = "0",
        func_code: int = 5,  # 遥控默认使用写单线圈功能码
        name: str = "",
        code: str = "",
        value: int = 0,
        frame_type: int = 2,  # 遥控帧类型
        decode: str = "0x20",
        related_yx_address: Optional[int] = None,
        command_type: int = 0,
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
        self._related_yx_address: Optional[int] = related_yx_address
        self._command_type: int = command_type  # 命令类型：0-合闸/1-分闸 等

    def list(self):
        """返回遥控点属性列表"""
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

    # ===== 遥控特有属性 =====

    @property
    def bit(self) -> int:
        return self._bit

    @bit.setter
    def bit(self, bit: int):
        self._bit = bit

    @property
    def related_yx_address(self) -> Optional[int]:
        """关联的遥信点地址"""
        return self._related_yx_address

    @related_yx_address.setter
    def related_yx_address(self, address: int):
        self._related_yx_address = address

    @property
    def command_type(self) -> int:
        """命令类型"""
        return self._command_type

    @command_type.setter
    def command_type(self, cmd_type: int):
        self._command_type = cmd_type

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        """设置遥控值"""
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
        """设置遥控真实值（仅允许 0 或 1）"""
        if 0 <= int(real_value) <= 1:
            self.value = int(real_value)
            return True
        else:
            return False

    @property
    def real_value(self):
        """遥控的真实值就是其值本身"""
        return self._value

    @real_value.setter
    def real_value(self, value):
        self._value = value

    def execute(self) -> bool:
        """执行遥控命令（预留方法，实际执行逻辑由协议层处理）"""
        # TODO: 可添加命令执行前的校验逻辑
        return True
