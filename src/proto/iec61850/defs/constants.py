"""IEC 61850 协议常量定义

包含 pyiec61850 可用性检测、功能约束 (FC) 常量、
IEC 数据类型枚举、帧类型枚举、ACSI 类常量等。
"""

from enum import IntEnum, StrEnum

# ===== pyiec61850 可用性检测 =====
try:
    from pyiec61850 import pyiec61850 as _iec61850

    HAS_IEC61850 = True
except ImportError:
    _iec61850 = None
    HAS_IEC61850 = False

# ===== 功能约束 (FunctionalConstraint) - 运行时常量 =====
# 来自 pyiec61850，仅在 HAS_IEC61850 时有值
FC_MX = getattr(_iec61850, "IEC61850_FC_MX", None)  # 测量值
FC_ST = getattr(_iec61850, "IEC61850_FC_ST", None)  # 状态
FC_CO = getattr(_iec61850, "IEC61850_FC_CO", None)  # 控制
FC_CF = getattr(_iec61850, "IEC61850_FC_CF", None)  # 配置
FC_DC = getattr(_iec61850, "IEC61850_FC_DC", None)  # 描述
FC_RP = getattr(_iec61850, "IEC61850_FC_RP", None)  # 未缓冲报告 (URCB)
FC_BR = getattr(_iec61850, "IEC61850_FC_BR", None)  # 缓冲报告 (BRCB)


class FunctionalConstraint(StrEnum):
    """功能约束枚举"""

    MX = "MX"  # 测量值
    ST = "ST"  # 状态
    CO = "CO"  # 控制
    CF = "CF"  # 配置
    DC = "DC"  # 描述
    GO = "GO"  # GOOSE
    SV = "SV"  # 替代值
    BL = "BL"  # 闭锁
    OR = "OR"  # 来源
    SP = "SP"  # 设定参数
    SE = "SE"  # 设定编辑
    EX = "EX"  # 扩展定义
    SG = "SG"  # 定值组
    SR = "SR"  # 定值组响应
    US = "US"  # 单元状态
    MS = "MS"  # 多单元状态
    RP = "RP"  # 未缓冲报告


# ===== IEC 61850 数据类型 =====
class IecType(StrEnum):
    """IEC 61850 数据类型枚举"""

    FLOAT = "float"
    BOOLEAN = "boolean"
    INTEGER = "integer"
    STRING = "string"
    TIMESTAMP = "timestamp"
    UNKNOWN = "unknown"


# IecType 枚举值别名 (保持旧常量名可用，通过 defs/__init__.py 统一导出)
IEC_TYPE_FLOAT = IecType.FLOAT
IEC_TYPE_BOOLEAN = IecType.BOOLEAN
IEC_TYPE_INTEGER = IecType.INTEGER
IEC_TYPE_STRING = IecType.STRING
IEC_TYPE_TIMESTAMP = IecType.TIMESTAMP
IEC_TYPE_UNKNOWN = IecType.UNKNOWN


# ===== 遥测/遥信/遥控/遥调 帧类型 =====
class FrameType(IntEnum):
    """帧类型枚举"""

    YC = 0  # 遥测
    YX = 1  # 遥信
    YK = 2  # 遥控
    YT = 3  # 遥调


FRAME_TYPE_DESC = {
    FrameType.YC: "遥测(YC)",
    FrameType.YX: "遥信(YX)",
    FrameType.YK: "遥控(YK)",
    FrameType.YT: "遥调(YT)",
}


# ===== ACSI 类常量 =====
class AcsiClass(IntEnum):
    """ACSI 类枚举 (值对应 pyiec61850 ACSIClass)"""

    DATA_OBJECT = getattr(_iec61850, "ACSI_CLASS_DATA_OBJECT", 0)
    DATA_SET = getattr(_iec61850, "ACSI_CLASS_DATA_SET", 1)
    BRCB = getattr(_iec61850, "ACSI_CLASS_BRCB", 2)
    URCB = getattr(_iec61850, "ACSI_CLASS_URCB", 3)
    GOOSE = getattr(_iec61850, "ACSI_CLASS_GoCB", 7)


# ===== FC -> FrameType 推断映射 =====
FC_TO_FRAME_TYPE: dict[str, FrameType] = {
    "MX": FrameType.YC,
    "ST": FrameType.YX,
    "CO": FrameType.YK,  # 遥控/遥调共用 CO
}

FRAME_TYPE_TO_FC: dict[FrameType, str] = {
    FrameType.YC: "MX",
    FrameType.YX: "ST",
    FrameType.YK: "CO",
    FrameType.YT: "CO",
}
