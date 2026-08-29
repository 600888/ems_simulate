"""Validated point-level DNP3 behavior shared by handlers and persistence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from pydnp3_pure.app.constants import PointFlags


@dataclass(slots=True)
class Dnp3PointConfig:
    static_variation: int
    event_variation: int
    event_class: int = 1
    deadband: float = 0.0
    control_mode: str = "direct"
    crob_operation: str = "latch"
    pulse_on_ms: int = 100
    pulse_off_ms: int = 100
    pulse_count: int = 1
    initial_quality: int = int(PointFlags.ONLINE)
    event_enabled: bool = True
    timestamp_enabled: bool = True

    @classmethod
    def defaults(cls, frame_type: int) -> Dnp3PointConfig:
        """按测点类型返回默认静态/事件变体与事件类别配置。"""
        variations = {
            0: (5, 7),
            1: (2, 2),
            2: (2, 1),
            3: (3, 3),
        }
        static, event = variations.get(frame_type, variations[0])
        return cls(
            static_variation=static,
            event_variation=event,
            event_class=2 if frame_type in (2, 3) else 1,
            event_enabled=frame_type in (0, 1),
        )

    @classmethod
    def from_mapping(cls, frame_type: int, values: dict[str, Any] | None) -> Dnp3PointConfig:
        """从配置字典构造配置对象并校验合法性。"""
        result = cls.defaults(frame_type)
        for name, value in (values or {}).items():
            if hasattr(result, name):
                setattr(result, name, value)
        result.validate(frame_type)
        return result

    def validate(self, frame_type: int) -> None:
        """校验各字段取值，非法则抛出 ValueError。"""
        allowed_static = {0: {1, 2, 3, 4, 5, 6}, 1: {1, 2}, 2: {1, 2}, 3: {1, 2, 3, 4}}[frame_type]
        allowed_event = {0: {1, 2, 3, 4, 5, 6, 7, 8}, 1: {1, 2, 3}, 2: {1, 2}, 3: {1, 2, 3, 4, 5, 6, 7, 8}}[frame_type]
        if self.static_variation not in allowed_static:
            raise ValueError(f"DNP3静态变体不适用于当前点类型: V{self.static_variation}")
        if self.event_variation not in allowed_event:
            raise ValueError(f"DNP3事件变体不适用于当前点类型: V{self.event_variation}")
        if self.event_class not in (1, 2, 3):
            raise ValueError("DNP3事件类别必须是 1、2 或 3")
        if self.deadband < 0:
            raise ValueError("DNP3死区不能小于 0")
        if self.control_mode not in {"direct", "sbo"}:
            raise ValueError("DNP3控制模式必须是 direct 或 sbo")
        if self.crob_operation not in {"latch", "pulse"}:
            raise ValueError("DNP3 CROB 操作类型必须是 latch 或 pulse")
        if min(self.pulse_on_ms, self.pulse_off_ms) < 0 or self.pulse_count < 1:
            raise ValueError("DNP3脉冲时间不能为负且脉冲次数至少为 1")
        if not 0 <= self.initial_quality <= 0xFF:
            raise ValueError("DNP3初始品质必须在 0 到 255 之间")

    def to_dict(self) -> dict[str, Any]:
        """将配置对象导出为字典。"""
        return asdict(self)
