"""Typed DLT698 state exposed to the shared mapping, simulator and history UI."""

from copy import deepcopy
from decimal import ROUND_HALF_UP, Decimal
import json

from src.enums.points.yc import Yc
from src.proto.dlt698.schema import Data

SCALAR_TYPES = {"Int8", "UInt8", "Int16", "UInt16", "Int32", "UInt32", "Float32", "Float64"}


class Dlt698PointState(Yc):
    def __init__(self, definition, publish):
        super().__init__(code=definition["code"], name=definition["name"], address="0x" + definition["oad"])
        self.definition = definition
        self.data = deepcopy(definition["initial_value"])
        self.publish = publish
        self.scalar = definition["data_type"] in SCALAR_TYPES
        self._mul_coe = 10 ** definition["scaler"]
        self.min_value_limit = definition.get("min_value_limit", 0)
        self.max_value_limit = definition.get("max_value_limit", 100)

    @property
    def value(self):
        if not hasattr(self, "data"):
            return self._value
        value = self.data["value"]
        if self.data["type"].startswith(("Int", "UInt")):
            return int(value)
        if self.data["type"].startswith("Float"):
            return float(value)
        return json.dumps(value, ensure_ascii=False)

    @value.setter
    def value(self, value):
        if not hasattr(self, "data"):
            self._value = value
            return
        if not self.scalar:
            raise ValueError("此 Data 类型请使用 DL/T 698 有类型的编辑器")
        self.set_real_value(Decimal(str(value)) * Decimal(10) ** self.definition["scaler"])

    @property
    def real_value(self):
        if not hasattr(self, "data"):
            return self._real_value
        if self.data["type"].startswith(("Int", "UInt", "Float")):
            value = Decimal(self.data["value"]) * Decimal(10) ** self.definition["scaler"]
            return float(value) if self.scalar else format(value, "f")
        return json.dumps(self.data["value"], ensure_ascii=False)

    @real_value.setter
    def real_value(self, value):
        self._real_value = value

    def set_real_value(self, value):
        if not self.scalar:
            raise ValueError("复合值及 64 位整数请使用精确 Data 编辑器，不支持浮点模拟或映射")
        try:
            raw = Decimal(str(value)) / (Decimal(10) ** self.definition["scaler"])
            if self.data["type"].startswith(("Int", "UInt")):
                raw = raw.to_integral_value(rounding=ROUND_HALF_UP)
            data = Data(type=self.data["type"], value=format(raw, "f"))
            self.publish(self.definition["oad"], data)
        except (ValueError, ArithmeticError):
            return False
        return True

    def accept(self, data):
        data = deepcopy(data)
        if data == self.data:
            return
        old_value, old_real = self._display(self.data), self._engineering(self.data)
        self.data = data
        if self.change_tracking_enabled:
            self._record_change(old_value, self._display(data), old_real, self._engineering(data))
        if self.is_send_signal and self.scalar:
            self.value_changed.send(self, old_point=self, related_point=self.related_point)

    @staticmethod
    def _display(data):
        value = data["value"]
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    def _engineering(self, data):
        if data["type"].startswith(("Int", "UInt", "Float")):
            return format(Decimal(data["value"]) * Decimal(10) ** self.definition["scaler"], "f")
        return self._display(data)
