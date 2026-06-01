"""
IEC 60870-5-104 品质描述符模块

IEC 104 协议中，不同 ASDU 类型有不同的品质描述符格式：
- 遥测 (M_ME_*): QDS (Quality Descriptor) — OV/BL/SB/NT/IV
- 单点遥信 (M_SP_*): SIQ (Single-point Information Quality) — SPI/BL/SB/NT/IV
- 双点遥信 (M_DP_*): DIQ (Double-point Information Quality) — DPI/BL/SB/NT/IV
- 遥控 (C_SC/DC/RC_*): 无品质描述符（控制方向）
- 遥调 (C_SE_*): QDS — OV/BL/SB/NT/IV

品质描述符各标志位含义：
    OV (Overflow):       溢出 — 遥测/遥调值超出表示范围
    BL (Blocked):        闭锁 — 值被闭锁（例如现场检修时闭锁）
    SB (Substituted):    取代 — 值被手动/自动取代
    NT (Not Topical):    不刷新 — 值未更新（非真实值）
    IV (Invalid):        无效 — 值无效（设备故障等）

设计模式:
    - IntFlag: 位标志枚举，支持位运算组合
    - dataclass: 品质描述符的结构化表示
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntFlag
from typing import Optional

# ===== 品质标志位枚举 =====


class IEC104QualityFlag(IntFlag):
    """IEC104 品质描述符标志位

    使用 IntFlag 支持位运算组合，例如：
        flags = IEC104QualityFlag.OV | IEC104QualityFlag.IV
        if IEC104QualityFlag.OV in flags: ...
    """

    NONE = 0  # 无标志
    OV = 0x01  # 溢出 (Overflow) — 仅遥测/遥调
    BL = 0x02  # 闭锁 (Blocked)
    SB = 0x04  # 取代 (Substituted)
    NT = 0x08  # 不刷新 (Not Topical)
    IV = 0x10  # 无效 (Invalid)

    @property
    def label(self) -> str:
        """返回中文标签"""
        labels = {
            0x01: "溢出",
            0x02: "闭锁",
            0x04: "取代",
            0x08: "不刷新",
            0x10: "无效",
        }
        return labels.get(self.value, str(self.value))

    def to_labels(self) -> list[str]:
        """返回所有激活标志的中文标签列表"""
        result = []
        if self.OV in self:
            result.append("溢出")
        if self.BL in self:
            result.append("闭锁")
        if self.SB in self:
            result.append("取代")
        if self.NT in self:
            result.append("不刷新")
        if self.IV in self:
            result.append("无效")
        return result

    def to_dict(self) -> dict[str, bool]:
        """返回各标志位的布尔值字典"""
        return {
            "ov": bool(self.OV in self),
            "bl": bool(self.BL in self),
            "sb": bool(self.SB in self),
            "nt": bool(self.NT in self),
            "iv": bool(self.IV in self),
        }

    @classmethod
    def from_dict(cls, data: dict[str, bool]) -> IEC104QualityFlag:
        """从布尔值字典创建标志位组合"""
        flags = cls.NONE
        if data.get("ov", False):
            flags |= cls.OV
        if data.get("bl", False):
            flags |= cls.BL
        if data.get("sb", False):
            flags |= cls.SB
        if data.get("nt", False):
            flags |= cls.NT
        if data.get("iv", False):
            flags |= cls.IV
        return flags

    @classmethod
    def from_int(cls, value: int) -> IEC104QualityFlag:
        """从整数值创建标志位"""
        return cls(value & 0x1F)  # 只取低5位


# ===== 品质描述符结构体 =====


@dataclass
class IEC104QualityDescriptor:
    """IEC104 品质描述符

    为测点提供结构化的品质信息管理。
    内部使用整数值存储，提供便捷的布尔属性访问。

    Attributes:
        overflow: 溢出标志（仅遥测/遥调有效）
        blocked: 闭锁标志
        substituted: 取代标志
        not_topical: 不刷新标志
        invalid: 无效标志
    """

    overflow: bool = False
    blocked: bool = False
    substituted: bool = False
    not_topical: bool = False
    invalid: bool = False

    def to_int(self) -> int:
        """转换为整数值（用于数据库存储和协议传输）"""
        value = 0
        if self.overflow:
            value |= 0x01
        if self.blocked:
            value |= 0x02
        if self.substituted:
            value |= 0x04
        if self.not_topical:
            value |= 0x08
        if self.invalid:
            value |= 0x10
        return value

    @classmethod
    def from_int(cls, value: int) -> IEC104QualityDescriptor:
        """从整数值创建品质描述符"""
        if value is None:
            return cls()
        value = int(value)
        return cls(
            overflow=bool(value & 0x01),
            blocked=bool(value & 0x02),
            substituted=bool(value & 0x04),
            not_topical=bool(value & 0x08),
            invalid=bool(value & 0x10),
        )

    def to_flags(self) -> IEC104QualityFlag:
        """转换为标志位枚举"""
        return IEC104QualityFlag.from_int(self.to_int())

    @classmethod
    def from_flags(cls, flags: IEC104QualityFlag) -> IEC104QualityDescriptor:
        """从标志位枚举创建"""
        return cls.from_int(flags.value)

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "overflow": self.overflow,
            "blocked": self.blocked,
            "substituted": self.substituted,
            "not_topical": self.not_topical,
            "invalid": self.invalid,
            "value": self.to_int(),
            "labels": self.to_labels(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> IEC104QualityDescriptor:
        """从字典反序列化"""
        return cls(
            overflow=data.get("overflow", False),
            blocked=data.get("blocked", False),
            substituted=data.get("substituted", False),
            not_topical=data.get("not_topical", False),
            invalid=data.get("invalid", False),
        )

    def to_labels(self) -> list[str]:
        """返回所有激活标志的中文标签"""
        labels = []
        if self.overflow:
            labels.append("溢出")
        if self.blocked:
            labels.append("闭锁")
        if self.substituted:
            labels.append("取代")
        if self.not_topical:
            labels.append("不刷新")
        if self.invalid:
            labels.append("无效")
        return labels

    def __str__(self) -> str:
        labels = self.to_labels()
        return ", ".join(labels) if labels else "正常"

    def __bool__(self) -> bool:
        """是否有任何品质标志被设置"""
        return self.overflow or self.blocked or self.substituted or self.not_topical or self.invalid


# ===== 品质描述符与 ASDU 类型的关系 =====


def supports_overflow(frame_type: int) -> bool:
    """判断该帧类型是否支持溢出(OV)标志

    只有遥测(frame_type=0)和遥调(frame_type=3)支持 OV 标志。
    遥信和遥控不支持。
    """
    return frame_type in (0, 3)


def supports_quality(frame_type: int) -> bool:
    """判断该帧类型是否支持品质描述符

    遥控(frame_type=2)为控制方向，不携带品质描述符。
    """
    return frame_type in (0, 1, 3)


def get_quality_descriptor_for_frame_type(frame_type: int) -> str:
    """获取帧类型对应的品质描述符名称"""
    names = {
        0: "QDS",  # Quality Descriptor (遥测)
        1: "SIQ/DIQ",  # Single/Double-point Information Quality (遥信)
        2: "无",  # 遥控不带品质
        3: "QDS",  # Quality Descriptor (遥调)
    }
    return names.get(frame_type, "未知")


# ===== c104 库品质位映射 =====
# c104 库使用的品质位编码与应用层不同：
#   应用层: OV=0x01, BL=0x02, SB=0x04, NT=0x08, IV=0x10
#   c104库: OV=0x01, BL=0x10, SB=0x20, NT=0x40, IV=0x80, ETI=0x08
_C104_QUALITY_MASK = {
    "OV": 0x01,  # Overflow
    "BL": 0x10,  # Blocked
    "SB": 0x20,  # Substituted
    "NT": 0x40,  # NonTopical
    "IV": 0x80,  # Invalid
    "ETI": 0x08,  # ElapsedTimeInvalid (c104 库特有)
}

# 应用层品质位 → c104 品质位
_APP_TO_C104 = {
    0x01: _C104_QUALITY_MASK["OV"],  # OV
    0x02: _C104_QUALITY_MASK["BL"],  # BL
    0x04: _C104_QUALITY_MASK["SB"],  # SB
    0x08: _C104_QUALITY_MASK["NT"],  # NT
    0x10: _C104_QUALITY_MASK["IV"],  # IV
}

# c104 品质位 → 应用层品质位
_C104_TO_APP = {v: k for k, v in _APP_TO_C104.items()}


def _app_quality_to_c104(app_value: int) -> int:
    """将应用层品质整数值转换为 c104 库品质整数值"""
    c104_value = 0
    for app_bit, c104_bit in _APP_TO_C104.items():
        if app_value & app_bit:
            c104_value |= c104_bit
    return c104_value


def _c104_quality_to_app(c104_value: int) -> int:
    """将 c104 库品质整数值转换为应用层品质整数值"""
    app_value = 0
    for c104_bit, app_bit in _C104_TO_APP.items():
        if c104_value & c104_bit:
            app_value |= app_bit
    return app_value


def decode_quality_from_c104(point, frame_type: int) -> IEC104QualityDescriptor:
    """从 c104 Point 对象解码品质描述符

    c104 库的 Point 对象包含 quality 属性，读取后转换为 IEC104QualityDescriptor。
    注意：c104 库的品质位编码与应用层不同，需要转换。

    Args:
        point: c104.Point 对象
        frame_type: 帧类型

    Returns:
        品质描述符对象
    """
    try:
        if hasattr(point, "quality") and point.quality is not None:
            c104_quality_int = int(point.quality)
            app_quality_int = _c104_quality_to_app(c104_quality_int)
            return IEC104QualityDescriptor.from_int(app_quality_int)
    except Exception:
        pass
    return IEC104QualityDescriptor()


def encode_quality_for_c104(quality: IEC104QualityDescriptor, frame_type: int) -> int:
    """将品质描述符编码为 c104 可接受的整数值

    c104 库使用不同的品质位编码，此处完成应用层→c104库的转换。
    对于不支持 OV 的帧类型，自动清除 OV 位。

    Args:
        quality: 品质描述符对象
        frame_type: 帧类型

    Returns:
        编码后的品质整数值（c104 库格式）
    """
    # 遥控不带品质
    if frame_type == 2:
        return 0

    app_value = quality.to_int()
    # 遥信不支持 OV
    if frame_type == 1:
        app_value &= ~0x01  # 清除 OV 位

    # 转换为 c104 库编码
    return _app_quality_to_c104(app_value)
