"""
IEC 60870-5-104 ASDU 类型定义模块

使用现代 Python 设计模式（StrEnum + dataclass）定义所有 IEC104 ASDU 类型，
提供类型安全的类型标识、分类和元数据管理。

Design Patterns:
    - StrEnum: 类型标识枚举，支持字符串比较和序列化
    - frozen dataclass: 不可变类型元数据
    - 类方法工厂: 按帧类型/方向筛选可用类型
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class IEC104Direction(StrEnum):
    """IEC104 传输方向"""

    MONITORING = "monitoring"  # 监视方向（服务端→客户端）
    CONTROL = "control"  # 控制方向（客户端→服务端）


class IEC104ValueType(StrEnum):
    """IEC104 值数据类型"""

    FLOAT = "float"  # 浮点数（归一化/标度化/短浮点遥测、短浮点遥调）
    INTEGER = "integer"  # 整数（归一化/标度化遥调）
    SINGLE = "single"  # 单点（开/关，SIQ）
    DOUBLE = "double"  # 双点（合/分/中间/不确定，DIQ）
    STEP = "step"  # 步位置（升降）


@dataclass(frozen=True, slots=True)
class IEC104TypeInfo:
    """IEC104 ASDU 类型元数据（不可变）

    Attributes:
        type_id: ASDU 类型标识符（如 M_ME_NC_1）
        type_code: ASDU 类型编号（如 13）
        label: 中文标签
        direction: 传输方向
        value_type: 值数据类型
        frame_type: 对应的帧类型（0=遥测, 1=遥信, 2=遥控, 3=遥调）
        has_timestamp: 是否带时标
        timestamp_type: 时标类型（None/CP16/CP56）
    """

    type_id: str
    type_code: int
    label: str
    direction: IEC104Direction
    value_type: IEC104ValueType
    frame_type: int
    has_timestamp: bool = False
    timestamp_type: str | None = None


class IEC104Type(StrEnum):
    """IEC104 ASDU 类型标识枚举

    每个成员值即为标准类型标识符字符串（如 "M_ME_NC_1"），
    可直接用于 c104.Type 查找和数据库存储。

    用法:
        t = IEC104Type.M_ME_NC_1
        info = IEC104_TYPE_REGISTRY[t]
        print(info.label)       # "短浮点遥测"
        print(info.frame_type)  # 0
    """

    # ===== 监视方向 - 遥测 (frame_type=0) =====
    M_ME_NA_1 = "M_ME_NA_1"  # 归一化遥测
    M_ME_NB_1 = "M_ME_NB_1"  # 标度化遥测
    M_ME_NC_1 = "M_ME_NC_1"  # 短浮点遥测
    M_ME_ND_1 = "M_ME_ND_1"  # 归一化遥测(不带品质)
    M_ME_TD_1 = "M_ME_TD_1"  # 归一化遥测(CP56)
    M_ME_TE_1 = "M_ME_TE_1"  # 标度化遥测(CP56)
    M_ME_TF_1 = "M_ME_TF_1"  # 短浮点遥测(CP56)

    # ===== 监视方向 - 遥信 (frame_type=1) =====
    M_SP_NA_1 = "M_SP_NA_1"  # 单点遥信
    M_SP_TA_1 = "M_SP_TA_1"  # 单点遥信(带时标CP16)
    M_DP_NA_1 = "M_DP_NA_1"  # 双点遥信
    M_DP_TA_1 = "M_DP_TA_1"  # 双点遥信(带时标CP16)
    M_SP_TB_1 = "M_SP_TB_1"  # 单点遥信(CP56)
    M_DP_TB_1 = "M_DP_TB_1"  # 双点遥信(CP56)

    # ===== 控制方向 - 遥控 (frame_type=2) =====
    C_SC_NA_1 = "C_SC_NA_1"  # 单点遥控
    C_DC_NA_1 = "C_DC_NA_1"  # 双点遥控
    C_RC_NA_1 = "C_RC_NA_1"  # 步调节命令
    C_SC_TA_1 = "C_SC_TA_1"  # 单点遥控(CP56)
    C_DC_TA_1 = "C_DC_TA_1"  # 双点遥控(CP56)
    C_RC_TA_1 = "C_RC_TA_1"  # 步调节命令(CP56)

    # ===== 控制方向 - 遥调 (frame_type=3) =====
    C_SE_NA_1 = "C_SE_NA_1"  # 设定值(归一化)
    C_SE_NB_1 = "C_SE_NB_1"  # 设定值(标度化)
    C_SE_NC_1 = "C_SE_NC_1"  # 设定值(短浮点)
    C_SE_TA_1 = "C_SE_TA_1"  # 设定值归一化(CP56)
    C_SE_TB_1 = "C_SE_TB_1"  # 设定值标度化(CP56)
    C_SE_TC_1 = "C_SE_TC_1"  # 设定值短浮点(CP56)


# ===== 类型元数据注册表 =====
IEC104_TYPE_REGISTRY: dict[IEC104Type, IEC104TypeInfo] = {
    # --- 遥测 ---
    IEC104Type.M_ME_NA_1: IEC104TypeInfo(
        "M_ME_NA_1", 9, "归一化遥测", IEC104Direction.MONITORING, IEC104ValueType.FLOAT, 0
    ),
    IEC104Type.M_ME_NB_1: IEC104TypeInfo(
        "M_ME_NB_1", 11, "标度化遥测", IEC104Direction.MONITORING, IEC104ValueType.FLOAT, 0
    ),
    IEC104Type.M_ME_NC_1: IEC104TypeInfo(
        "M_ME_NC_1", 13, "短浮点遥测", IEC104Direction.MONITORING, IEC104ValueType.FLOAT, 0
    ),
    IEC104Type.M_ME_ND_1: IEC104TypeInfo(
        "M_ME_ND_1", 21, "归一化遥测(不带品质)", IEC104Direction.MONITORING, IEC104ValueType.FLOAT, 0
    ),
    IEC104Type.M_ME_TD_1: IEC104TypeInfo(
        "M_ME_TD_1", 34, "归一化遥测(CP56)", IEC104Direction.MONITORING, IEC104ValueType.FLOAT, 0, True, "CP56"
    ),
    IEC104Type.M_ME_TE_1: IEC104TypeInfo(
        "M_ME_TE_1", 35, "标度化遥测(CP56)", IEC104Direction.MONITORING, IEC104ValueType.FLOAT, 0, True, "CP56"
    ),
    IEC104Type.M_ME_TF_1: IEC104TypeInfo(
        "M_ME_TF_1", 36, "短浮点遥测(CP56)", IEC104Direction.MONITORING, IEC104ValueType.FLOAT, 0, True, "CP56"
    ),
    # --- 遥信 ---
    IEC104Type.M_SP_NA_1: IEC104TypeInfo(
        "M_SP_NA_1", 1, "单点遥信", IEC104Direction.MONITORING, IEC104ValueType.SINGLE, 1
    ),
    IEC104Type.M_SP_TA_1: IEC104TypeInfo(
        "M_SP_TA_1", 2, "单点遥信(带时标)", IEC104Direction.MONITORING, IEC104ValueType.SINGLE, 1, True, "CP16"
    ),
    IEC104Type.M_DP_NA_1: IEC104TypeInfo(
        "M_DP_NA_1", 3, "双点遥信", IEC104Direction.MONITORING, IEC104ValueType.DOUBLE, 1
    ),
    IEC104Type.M_DP_TA_1: IEC104TypeInfo(
        "M_DP_TA_1", 4, "双点遥信(带时标)", IEC104Direction.MONITORING, IEC104ValueType.DOUBLE, 1, True, "CP16"
    ),
    IEC104Type.M_SP_TB_1: IEC104TypeInfo(
        "M_SP_TB_1", 30, "单点遥信(CP56)", IEC104Direction.MONITORING, IEC104ValueType.SINGLE, 1, True, "CP56"
    ),
    IEC104Type.M_DP_TB_1: IEC104TypeInfo(
        "M_DP_TB_1", 31, "双点遥信(CP56)", IEC104Direction.MONITORING, IEC104ValueType.DOUBLE, 1, True, "CP56"
    ),
    # --- 遥控 ---
    IEC104Type.C_SC_NA_1: IEC104TypeInfo(
        "C_SC_NA_1", 45, "单点遥控", IEC104Direction.CONTROL, IEC104ValueType.SINGLE, 2
    ),
    IEC104Type.C_DC_NA_1: IEC104TypeInfo(
        "C_DC_NA_1", 46, "双点遥控", IEC104Direction.CONTROL, IEC104ValueType.DOUBLE, 2
    ),
    IEC104Type.C_RC_NA_1: IEC104TypeInfo(
        "C_RC_NA_1", 47, "步调节命令", IEC104Direction.CONTROL, IEC104ValueType.STEP, 2
    ),
    IEC104Type.C_SC_TA_1: IEC104TypeInfo(
        "C_SC_TA_1", 58, "单点遥控(CP56)", IEC104Direction.CONTROL, IEC104ValueType.SINGLE, 2, True, "CP56"
    ),
    IEC104Type.C_DC_TA_1: IEC104TypeInfo(
        "C_DC_TA_1", 59, "双点遥控(CP56)", IEC104Direction.CONTROL, IEC104ValueType.DOUBLE, 2, True, "CP56"
    ),
    IEC104Type.C_RC_TA_1: IEC104TypeInfo(
        "C_RC_TA_1", 60, "步调节命令(CP56)", IEC104Direction.CONTROL, IEC104ValueType.STEP, 2, True, "CP56"
    ),
    # --- 遥调 ---
    IEC104Type.C_SE_NA_1: IEC104TypeInfo(
        "C_SE_NA_1", 48, "设定值(归一化)", IEC104Direction.CONTROL, IEC104ValueType.FLOAT, 3
    ),
    IEC104Type.C_SE_NB_1: IEC104TypeInfo(
        "C_SE_NB_1", 49, "设定值(标度化)", IEC104Direction.CONTROL, IEC104ValueType.FLOAT, 3
    ),
    IEC104Type.C_SE_NC_1: IEC104TypeInfo(
        "C_SE_NC_1", 50, "设定值(短浮点)", IEC104Direction.CONTROL, IEC104ValueType.FLOAT, 3
    ),
    IEC104Type.C_SE_TA_1: IEC104TypeInfo(
        "C_SE_TA_1", 61, "设定值归一化(CP56)", IEC104Direction.CONTROL, IEC104ValueType.FLOAT, 3, True, "CP56"
    ),
    IEC104Type.C_SE_TB_1: IEC104TypeInfo(
        "C_SE_TB_1", 62, "设定值标度化(CP56)", IEC104Direction.CONTROL, IEC104ValueType.FLOAT, 3, True, "CP56"
    ),
    IEC104Type.C_SE_TC_1: IEC104TypeInfo(
        "C_SE_TC_1", 63, "设定值短浮点(CP56)", IEC104Direction.CONTROL, IEC104ValueType.FLOAT, 3, True, "CP56"
    ),
}

# ===== 快速查找索引 =====
_TYPE_CODE_MAP: dict[int, IEC104Type] = {info.type_code: t for t, info in IEC104_TYPE_REGISTRY.items()}

# 每个 frame_type 的默认类型（向后兼容）
IEC104_DEFAULT_TYPE: dict[int, IEC104Type] = {
    0: IEC104Type.M_ME_NC_1,  # 遥测默认短浮点
    1: IEC104Type.M_SP_NA_1,  # 遥信默认单点
    2: IEC104Type.C_SC_NA_1,  # 遥控默认单点
    3: IEC104Type.C_SE_NC_1,  # 遥调默认短浮点
}


def get_iec104_types_by_frame_type(frame_type: int) -> list[IEC104TypeInfo]:
    """获取指定帧类型的所有可用 IEC104 类型列表

    Args:
        frame_type: 帧类型 (0=遥测, 1=遥信, 2=遥控, 3=遥调)

    Returns:
        该帧类型下所有可用类型的元数据列表（默认类型排在首位）
    """
    default_type = IEC104_DEFAULT_TYPE.get(frame_type)
    types = [info for info in IEC104_TYPE_REGISTRY.values() if info.frame_type == frame_type]
    # 默认类型排在首位
    if default_type:
        types.sort(key=lambda t: (t.type_id != default_type.value, t.type_code))
    return types


def get_iec104_type_info(type_id: str) -> IEC104TypeInfo | None:
    """根据类型标识符获取元数据

    Args:
        type_id: ASDU 类型标识（如 "M_ME_NC_1"）

    Returns:
        类型元数据，不存在返回 None
    """
    try:
        return IEC104_TYPE_REGISTRY[IEC104Type(type_id)]
    except (ValueError, KeyError):
        return None


def get_iec104_type_by_code(type_code: int) -> IEC104Type | None:
    """根据 ASDU 类型编号获取枚举

    Args:
        type_code: ASDU 类型编号（如 13）

    Returns:
        枚举成员，不存在返回 None
    """
    return _TYPE_CODE_MAP.get(type_code)


def get_default_iec104_type(frame_type: int) -> IEC104Type:
    """获取帧类型对应的默认 IEC104 类型（向后兼容）

    Args:
        frame_type: 帧类型 (0-3)

    Returns:
        默认类型枚举
    """
    return IEC104_DEFAULT_TYPE.get(frame_type, IEC104Type.M_ME_NC_1)


def resolve_iec104_type(type_id: str | None, frame_type: int) -> IEC104Type:
    """解析 IEC104 类型：优先使用指定类型，否则回退到默认类型

    Args:
        type_id: 可选的类型标识符
        frame_type: 帧类型（用于回退默认值）

    Returns:
        解析后的 IEC104 类型枚举
    """
    if type_id:
        try:
            t = IEC104Type(type_id)
            # 验证类型与帧类型匹配
            info = IEC104_TYPE_REGISTRY[t]
            if info.frame_type == frame_type:
                return t
        except ValueError:
            pass
    return get_default_iec104_type(frame_type)


def is_double_point_type(type_id: str | None) -> bool:
    """判断是否为双点类型（双点遥信/双点遥控）

    Args:
        type_id: 类型标识符

    Returns:
        是否为双点类型
    """
    if not type_id:
        return False
    info = get_iec104_type_info(type_id)
    return info is not None and info.value_type == IEC104ValueType.DOUBLE


def is_step_type(type_id: str | None) -> bool:
    """判断是否为步调节类型

    Args:
        type_id: 类型标识符

    Returns:
        是否为步调节类型
    """
    if not type_id:
        return False
    info = get_iec104_type_info(type_id)
    return info is not None and info.value_type == IEC104ValueType.STEP


def is_normalized_type(type_id: str | None) -> bool:
    """判断是否为归一化类型（NVA, 值范围 -1~+1 映射为 int16）

    Args:
        type_id: 类型标识符

    Returns:
        是否为归一化类型
    """
    if not type_id:
        return False
    return type_id in (
        IEC104Type.M_ME_NA_1.value,
        IEC104Type.M_ME_ND_1.value,
        IEC104Type.M_ME_TD_1.value,
        IEC104Type.C_SE_NA_1.value,
        IEC104Type.C_SE_TA_1.value,
    )


def is_scaled_type(type_id: str | None) -> bool:
    """判断是否为标度化类型（SVA, 值为 int16 整数）

    Args:
        type_id: 类型标识符

    Returns:
        是否为标度化类型
    """
    if not type_id:
        return False
    return type_id in (
        IEC104Type.M_ME_NB_1.value,
        IEC104Type.M_ME_TE_1.value,
        IEC104Type.C_SE_NB_1.value,
        IEC104Type.C_SE_TB_1.value,
    )


def is_short_float_type(type_id: str | None) -> bool:
    """判断是否为短浮点类型（IEEE 754 float, 4 字节）

    Args:
        type_id: 类型标识符

    Returns:
        是否为短浮点类型
    """
    if not type_id:
        return False
    return type_id in (
        IEC104Type.M_ME_NC_1.value,
        IEC104Type.M_ME_TF_1.value,
        IEC104Type.C_SE_NC_1.value,
        IEC104Type.C_SE_TC_1.value,
    )


def encode_iec104_value(real_value: float, type_id: str | None):
    """根据 IEC104 ASDU 类型对值进行编码，返回 c104 库可接受的类型

    c104 库对不同 ASDU 类型要求不同的值类型：
    - 归一化类型: 需要 c104.NormalizedFloat 对象（值域 -1.0 ~ +1.0）
    - 标度化类型: 需要 c104.Int16 对象
    - 短浮点类型: 直接使用 Python float
    - 其他类型: 直接使用 Python float/bool

    Args:
        real_value: 物理值（遥测的 real_value）
        type_id: IEC104 ASDU 类型标识

    Returns:
        c104 库可接受的值对象（NormalizedFloat、Int16、float 等）
    """
    import c104

    if is_normalized_type(type_id):
        # 归一化: c104 要求 NormalizedFloat，值域 -1.0 ~ +1.0
        normalized = max(-1.0, min(1.0, float(real_value)))
        return c104.NormalizedFloat(normalized)
    elif is_scaled_type(type_id):
        # 标度化: c104 要求 Int16
        return c104.Int16(int(round(real_value)))
    else:
        # 短浮点或其他: 直接 float
        return float(real_value)


def decode_iec104_value(raw_value, type_id: str | None) -> float:
    """将 c104 库读取的 point.value 转换为 Python float

    c104 库对不同 ASDU 类型返回不同的值类型：
    - 归一化类型: 返回 c104.NormalizedFloat，float() 后已是 -1~+1 范围的浮点数
    - 标度化类型: 返回 c104.Int16，float() 后已是标度值
    - 短浮点类型: 返回 Python float

    注意: c104 库已经在内部完成了 NVA→float 的转换，
    不需要再除以 32767，直接 float() 即可得到物理值。

    Args:
        raw_value: c104 库读取的原始值（可能是 NormalizedFloat、Int16、float 等）
        type_id: IEC104 ASDU 类型标识

    Returns:
        解码后的物理值（Python float）
    """
    return float(raw_value)
