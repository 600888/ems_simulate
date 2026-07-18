"""Native MMS type definitions and compatibility mappings."""

from __future__ import annotations

from enum import StrEnum

from .constants import IecType


class MmsType(StrEnum):
    """Wire-level MMS types exposed by libIEC61850."""

    ARRAY = "MMS_ARRAY"
    STRUCTURE = "MMS_STRUCTURE"
    BOOLEAN = "MMS_BOOLEAN"
    BIT_STRING = "MMS_BIT_STRING"
    INTEGER = "MMS_INTEGER"
    UNSIGNED = "MMS_UNSIGNED"
    FLOAT = "MMS_FLOAT"
    OCTET_STRING = "MMS_OCTET_STRING"
    VISIBLE_STRING = "MMS_VISIBLE_STRING"
    GENERALIZED_TIME = "MMS_GENERALIZED_TIME"
    BINARY_TIME = "MMS_BINARY_TIME"
    BCD = "MMS_BCD"
    OBJ_ID = "MMS_OBJ_ID"
    STRING = "MMS_STRING"
    UTC_TIME = "MMS_UTC_TIME"
    DATA_ACCESS_ERROR = "MMS_DATA_ACCESS_ERROR"
    UNKNOWN = "MMS_UNKNOWN"


NATIVE_MMS_TYPE_NAMES: tuple[str, ...] = tuple(item.value for item in MmsType if item is not MmsType.UNKNOWN)


def mms_type_from_native(native_type: int, native_module=None) -> MmsType:
    """把 pyiec61850 的原生类型常量映射为内部 MmsType。"""
    if native_module is not None:
        for item in MmsType:
            if item is MmsType.UNKNOWN:
                continue
            if native_type == getattr(native_module, item.value, object()):
                return item
        return MmsType.UNKNOWN

    # libIEC61850's MmsType enum values are stable and contiguous.
    names = (
        MmsType.ARRAY,
        MmsType.STRUCTURE,
        MmsType.BOOLEAN,
        MmsType.BIT_STRING,
        MmsType.INTEGER,
        MmsType.UNSIGNED,
        MmsType.FLOAT,
        MmsType.OCTET_STRING,
        MmsType.VISIBLE_STRING,
        MmsType.GENERALIZED_TIME,
        MmsType.BINARY_TIME,
        MmsType.BCD,
        MmsType.OBJ_ID,
        MmsType.STRING,
        MmsType.UTC_TIME,
        MmsType.DATA_ACCESS_ERROR,
    )
    return names[native_type] if 0 <= native_type < len(names) else MmsType.UNKNOWN


BTYPE_TO_MMS_TYPE: dict[str, MmsType] = {
    "BOOLEAN": MmsType.BOOLEAN,
    "INT8": MmsType.INTEGER,
    "INT16": MmsType.INTEGER,
    "INT24": MmsType.INTEGER,
    "INT32": MmsType.INTEGER,
    "INT64": MmsType.INTEGER,
    "INT128": MmsType.INTEGER,
    "INT8U": MmsType.UNSIGNED,
    "INT16U": MmsType.UNSIGNED,
    "INT24U": MmsType.UNSIGNED,
    "INT32U": MmsType.UNSIGNED,
    "FLOAT32": MmsType.FLOAT,
    "FLOAT64": MmsType.FLOAT,
    "Dbpos": MmsType.BIT_STRING,
    "Tcmd": MmsType.BIT_STRING,
    "Quality": MmsType.BIT_STRING,
    "Timestamp": MmsType.UTC_TIME,
    "EntryTime": MmsType.BINARY_TIME,
    "Check": MmsType.BIT_STRING,
    "OptFls": MmsType.BIT_STRING,
    "TrgOps": MmsType.BIT_STRING,
    "SvOptFls": MmsType.BIT_STRING,
    "Enum": MmsType.INTEGER,
    "Struct": MmsType.STRUCTURE,
    "Octet64": MmsType.OCTET_STRING,
    "Unicode255": MmsType.STRING,
    "ObjRef": MmsType.VISIBLE_STRING,
    "Currency": MmsType.VISIBLE_STRING,
    "VisString32": MmsType.VISIBLE_STRING,
    "VisString64": MmsType.VISIBLE_STRING,
    "VisString129": MmsType.VISIBLE_STRING,
    "VisString255": MmsType.VISIBLE_STRING,
}

_NORMALIZED_BTYPE_TO_MMS_TYPE = {key.upper(): value for key, value in BTYPE_TO_MMS_TYPE.items()}


def mms_type_from_btype(btype: str) -> MmsType:
    """把 SCL bType 映射为对应的 MMS 类型。"""
    return _NORMALIZED_BTYPE_TO_MMS_TYPE.get(str(btype or "").strip().upper(), MmsType.UNKNOWN)


MMS_TO_IEC_TYPE: dict[MmsType, IecType] = {
    MmsType.FLOAT: IecType.FLOAT,
    MmsType.BOOLEAN: IecType.BOOLEAN,
    MmsType.INTEGER: IecType.INTEGER,
    MmsType.UNSIGNED: IecType.INTEGER,
    MmsType.BCD: IecType.INTEGER,
    MmsType.BIT_STRING: IecType.INTEGER,
    MmsType.VISIBLE_STRING: IecType.STRING,
    MmsType.STRING: IecType.STRING,
    MmsType.OCTET_STRING: IecType.STRING,
    MmsType.OBJ_ID: IecType.STRING,
    MmsType.GENERALIZED_TIME: IecType.TIMESTAMP,
    MmsType.BINARY_TIME: IecType.TIMESTAMP,
    MmsType.UTC_TIME: IecType.TIMESTAMP,
}


IEC_TO_DEFAULT_MMS_TYPE: dict[IecType, MmsType] = {
    IecType.FLOAT: MmsType.FLOAT,
    IecType.BOOLEAN: MmsType.BOOLEAN,
    IecType.INTEGER: MmsType.INTEGER,
    IecType.STRING: MmsType.VISIBLE_STRING,
    IecType.TIMESTAMP: MmsType.UTC_TIME,
    IecType.UNKNOWN: MmsType.UNKNOWN,
}


def mms_type_from_iec_type(iec_type: str | IecType) -> MmsType:
    """把项目内部 IEC 数据类型映射为 MMS 类型。"""
    try:
        normalized = IecType(iec_type)
    except (TypeError, ValueError):
        return MmsType.UNKNOWN
    return IEC_TO_DEFAULT_MMS_TYPE.get(normalized, MmsType.UNKNOWN)


def iec_type_from_mms_type(mms_type: str | MmsType) -> IecType:
    """把 MMS 类型映射为项目内部 IEC 数据类型。"""
    try:
        normalized = MmsType(mms_type)
    except (TypeError, ValueError):
        return IecType.UNKNOWN
    return MMS_TO_IEC_TYPE.get(normalized, IecType.UNKNOWN)


def infer_mms_type_from_path(path: str, iec_type: str | IecType = IecType.UNKNOWN) -> MmsType:
    """根据标准数据属性路径推断 MMS 类型；无法确定时返回 UNKNOWN。"""
    leaf = str(path or "").split(".")[-1]
    if leaf in ("NamPlt", "PhyNam"):
        return MmsType.STRUCTURE
    # Standard system DO main values. Beh/Health use CDC=ENS and Mod uses
    # CDC=ENC; both encode their stVal enumeration as MMS integer.
    if leaf in ("Beh", "Health", "Mod"):
        return MmsType.INTEGER
    if leaf == "f":
        return MmsType.FLOAT
    if leaf == "i":
        return MmsType.INTEGER
    if leaf in ("ctlVal", "Test"):
        return MmsType.BOOLEAN
    if leaf in ("ctlNum", "onDur", "offDur", "numPls"):
        return MmsType.UNSIGNED
    if leaf in ("origin", "pulseConfig", "sVC"):
        return MmsType.STRUCTURE
    if leaf in ("q", "subQ", "Check"):
        return MmsType.BIT_STRING
    if leaf in ("t", "T"):
        return MmsType.UTC_TIME
    if leaf in ("dU", "du", "d", "vendor", "swRev", "configRev", "lnNs", "dataNs"):
        return MmsType.VISIBLE_STRING
    if leaf in ("orIdent", "subID"):
        return MmsType.OCTET_STRING
    return mms_type_from_iec_type(iec_type)
