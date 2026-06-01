"""
基础测点类模块
提取遥测、遥信、遥调、遥控的公共属性和方法
"""

import builtins
from collections import deque
from typing import Dict, List, Optional, Union

from blinker import Signal

from src.enums.points.change_tracker import (
    ChangeRecord,
    ChangeSource,
    get_current_client_info,
    get_current_detail,
    get_current_source,
)
from src.enums.points.iec104_quality import IEC104QualityDescriptor


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
        iec_type_id: Optional[str] = None,
        iec_quality: Optional[int] = None,
        fc: str = "",
    ) -> None:
        self._is_updating = False
        self._rtu_addr: int = int(rtu_addr)

        # Handle string addresses like IEC61850 paths
        if (
            isinstance(address, str)
            and not address.startswith("0x")
            and not address.isnumeric()
            and any(c.isalpha() and c.lower() not in "abcdef" for c in address)
        ):
            self._address = address
            self._hex_address = address
        else:
            self._address: int | str = int(address, 16) if isinstance(address, str) else int(address)
            self._hex_address: str = str(address)

        self._func_code: int = int(func_code)
        self._name: str = name
        self._code: str = code
        self._value: int = int(value)
        self._hex_value: str = decimal_to_hex_formatted(self._value)
        self._frame_type: int = frame_type
        self._is_simulated: bool = False
        self._is_plan: bool = False
        self._decode = decode
        self._iec_type_id: Optional[str] = iec_type_id
        self._iec_quality: IEC104QualityDescriptor = IEC104QualityDescriptor.from_int(iec_quality or 0)
        self._fc: str = fc

        self.is_send_signal = False
        self.related_point: Optional[BasePoint] = None
        self.related_value: dict[int, int] | None = None
        self.value_changed = Signal()
        self.is_signed = False
        self.is_valid: Optional[bool] = None  # 数据是否有效（None:未知, True:成功, False:失败）
        self.is_locked_by_mapping = False  # 是否被映射锁定（如果为True，则模拟器不应修改此值）

        # 变更追溯（默认开启）
        self._change_tracking_enabled: bool = True
        self._change_history_maxlen: int = 50
        self._change_history: deque[ChangeRecord] = deque(maxlen=self._change_history_maxlen)

    def list(self) -> list[str | int | bool]:
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
    def address(self) -> int | str:
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
    def decode(self) -> str:
        return getattr(self, "_decode", "0x20")

    @decode.setter
    def decode(self, decode: str):
        old_decode = getattr(self, "_decode", None)
        if old_decode != decode:
            self._decode = decode
            self._on_decode_changed(old_decode)

    def _on_decode_changed(self, old_decode: Optional[str]):
        """当解析码改变时触发此回调，子类可重写以处理解析码变更后的逻辑"""
        pass

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        """设置测点值，子类可重写以添加特定逻辑"""
        if not self._is_updating and value != self._value:
            self._is_updating = True
            try:
                old_value = self._value
                self._value = value
                if isinstance(value, int):
                    self._hex_value = decimal_to_hex_formatted(value)

                if self._change_tracking_enabled:  # 如果变更追踪已启用
                    self._record_change(old_value, value)

                if self.is_send_signal:
                    self.value_changed.send(self, old_point=self, related_point=self.related_point)
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
    def fc(self) -> str:
        """IEC61850 功能约束 (FC), 如 MX/ST/CO/DC 等"""
        return self._fc

    @fc.setter
    def fc(self, fc: str):
        self._fc = fc

    @property
    def iec_type_id(self) -> Optional[str]:
        """IEC104 ASDU 类型标识（如 M_ME_NC_1）"""
        return self._iec_type_id

    @iec_type_id.setter
    def iec_type_id(self, type_id: Optional[str]):
        self._iec_type_id = type_id

    @property
    def iec_quality(self) -> IEC104QualityDescriptor:
        """IEC104 品质描述符"""
        return self._iec_quality

    @iec_quality.setter
    def iec_quality(self, quality: IEC104QualityDescriptor):
        self._iec_quality = quality

    @property
    def iec_quality_value(self) -> int:
        """IEC104 品质描述符整数值（用于数据库存储）"""
        return self._iec_quality.to_int()

    @iec_quality_value.setter
    def iec_quality_value(self, value: int):
        """通过整数值设置品质描述符"""
        self._iec_quality = IEC104QualityDescriptor.from_int(value)

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

    # ===== 变更追溯 =====

    @property
    def change_tracking_enabled(self) -> bool:
        """变更追溯是否已启用"""
        return self._change_tracking_enabled

    def enable_change_tracking(self) -> None:
        """启用变更追溯"""
        self._change_tracking_enabled = True

    def disable_change_tracking(self) -> None:
        """禁用变更追溯"""
        self._change_tracking_enabled = False

    def set_change_history_maxlen(self, maxlen: int) -> None:
        """设置变更历史最大条数（上限100）"""
        maxlen = max(1, min(maxlen, 100))
        self._change_history_maxlen = maxlen
        # 重建 deque 保留已有数据
        old = list(self._change_history)
        self._change_history = deque(old, maxlen=maxlen)

    def clear_change_history(self) -> None:
        """清空变更历史"""
        self._change_history.clear()

    def _record_change(self, old_value, new_value, old_real_value=None, new_real_value=None) -> None:
        """记录一次测点值变更（从 ContextVar 读取变更原因）"""
        source = get_current_source()
        detail = get_current_detail()
        client_info = get_current_client_info()
        record = ChangeRecord(
            source=source,
            old_value=old_value,
            new_value=new_value,
            old_real_value=old_real_value,
            new_real_value=new_real_value,
            detail=detail,
            client_info=client_info,
        )
        self._change_history.append(record)

    @property
    def change_history(self) -> builtins.list[ChangeRecord]:
        """返回变更历史记录列表（从旧到新）"""
        return list(self._change_history)

    @property
    def last_change(self) -> Optional[ChangeRecord]:
        """返回最近一条变更记录"""
        return self._change_history[-1] if self._change_history else None
