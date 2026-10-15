"""Model-scoped IEC 61850 enumeration definitions (independent of native bindings)."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class EnumItem:
    ord: int
    literal: str
    desc: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ord": self.ord, "literal": self.literal, "desc": self.desc}


@dataclass(frozen=True, slots=True)
class EnumDefinition:
    type_id: str
    items: tuple[EnumItem, ...] = ()
    desc: str = ""

    @property
    def error(self) -> str:
        if not self.items:
            return f"枚举类型 {self.type_id} 没有选项"
        ords = [item.ord for item in self.items]
        if any(type(value) is not int or not -(2**31) <= value < 2**31 for value in ords):
            return f"枚举类型 {self.type_id} 的 ord 必须是 INT32 范围内的整数"
        if len(set(ords)) != len(ords):
            return f"枚举类型 {self.type_id} 存在重复 ord"
        return ""

    def validate_value(self, value: Any) -> int:
        """Validate the actual wire ordinal without coercing floats, bools or labels."""
        if self.error:
            raise ValueError(self.error)
        if type(value) is not int:
            raise ValueError(f"枚举 {self.type_id} 必须使用整数编码")
        if value not in {item.ord for item in self.items}:
            raise ValueError(f"值 {value} 不属于枚举 {self.type_id}")
        return value

    def to_dict(self) -> dict[str, Any]:
        return {"type_id": self.type_id, "desc": self.desc, "items": [item.to_dict() for item in self.items]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EnumDefinition":
        return cls(
            type_id=data["type_id"],
            items=tuple(EnumItem(item["ord"], item["literal"], item.get("desc", "")) for item in data["items"]),
            desc=data.get("desc", ""),
        )
