"""SCL 枚举常量 — CDC 分类、FC、bType 映射等"""

from enum import IntEnum

# ===== CDC (Common Data Class) 到测点类型的映射 =====

CDC_YC = frozenset({"MV", "CMV", "SAV", "WYE", "DEL", "SEQ", "HMV"})
CDC_YX = frozenset({"SPS", "DPS", "INS", "ENS", "ENC", "ACT", "ACD", "SEC", "BCR"})
CDC_YK = frozenset({"SPC", "DPC"})
CDC_YT = frozenset({"APC", "INC", "ASG", "ING", "SPG", "BAC"})

ALL_CDCS = CDC_YC | CDC_YX | CDC_YK | CDC_YT


class PointCategory(IntEnum):
    """测点分类 (帧类型)"""

    YC = 0  # 遥测
    YX = 1  # 遥信
    YK = 2  # 遥控
    YT = 3  # 遥调


# CDC → PointCategory 映射
CDC_CATEGORY_MAP: dict[str, PointCategory] = {}
for _cdc in CDC_YC:
    CDC_CATEGORY_MAP[_cdc] = PointCategory.YC
for _cdc in CDC_YX:
    CDC_CATEGORY_MAP[_cdc] = PointCategory.YX
for _cdc in CDC_YK:
    CDC_CATEGORY_MAP[_cdc] = PointCategory.YK
for _cdc in CDC_YT:
    CDC_CATEGORY_MAP[_cdc] = PointCategory.YT


# ===== CDC 主值 DA 路径映射 =====

CDC_VALUE_DA_PATH: dict[str, str] = {
    "MV": "mag.f",
    "CMV": "cVal.mag.f",
    "SAV": "instMag.f",
    "SPS": "stVal",
    "DPS": "stVal",
    "INS": "stVal",
    "ENS": "stVal",
    "ENC": "stVal",
    "ACT": "stVal",
    "ACD": "stVal",
    "SEC": "stVal",
    "BCR": "actVal",
    "SPC": "ctlVal",
    "DPC": "ctlVal",
    "APC": "setVal",
    "INC": "stVal",
    "ASG": "setMag.f",
    "ING": "setVal",
    "SPG": "setVal",
    "BAC": "setVal",
}

# 控制 CDC 的操作 DA 路径 (优先级高于 CDC_VALUE_DA_PATH)
CDC_CONTROL_DA_PATH: dict[str, str] = {
    "SPC": "Oper.ctlVal",
    "DPC": "Oper.ctlVal",
    "APC": "Oper.ctlVal",
    "INC": "Oper.ctlVal",
    "BAC": "Oper.ctlVal",
}

# CDC 默认 FC
CDC_DEFAULT_FC: dict[str, str] = {
    "MV": "MX",
    "CMV": "MX",
    "SAV": "MX",
    "WYE": "MX",
    "DEL": "MX",
    "SEQ": "MX",
    "HMV": "MX",
    "SPS": "ST",
    "DPS": "ST",
    "INS": "ST",
    "ENS": "ST",
    "ENC": "ST",
    "ACT": "ST",
    "ACD": "ST",
    "SEC": "ST",
    "BCR": "ST",
    "SPC": "CO",
    "DPC": "CO",
    "APC": "CO",
    "INC": "CO",
    "ASG": "SP",
    "ING": "SP",
    "SPG": "SP",
    "BAC": "CO",
}


# ===== 结构体 DA 到完整叶子 DA 路径映射 =====

STRUCT_DA_TO_FULL_PATH: dict[str, str] = {
    "mag": "mag.f",
    "instMag": "instMag.f",
    "cVal": "cVal.mag.f",
    "mxVal": "mxVal.f",
    "fCVal": "fCVal.mag.f",
    "wVal": "wVal.f",
    "setMag": "setMag.f",
    "Oper": "Oper.ctlVal",
    "SBOw": "SBOw.ctlVal",
    "Cancel": "Cancel.ctlVal",
    "origin": "origin.orCat",
}


# ===== bType 到 IEC 数据类型映射 =====

BTYPE_TO_IEC_TYPE: dict[str, str] = {
    "BOOLEAN": "boolean",
    "INT8": "integer",
    "INT16": "integer",
    "INT24": "integer",
    "INT32": "integer",
    "INT64": "integer",
    "INT128": "integer",
    "INT8U": "integer",
    "INT16U": "integer",
    "INT24U": "integer",
    "INT32U": "integer",
    "FLOAT32": "float",
    "FLOAT64": "float",
    "Dbpos": "integer",
    "Tcmd": "integer",
    "Quality": "bitstring",
    "Timestamp": "timestamp",
    "VisString32": "string",
    "VisString64": "string",
    "VisString129": "string",
    "VisString255": "string",
    "Octet64": "string",
    "Unicode255": "string",
    "EntryTime": "timestamp",
    "Check": "bitstring",
    "ObjRef": "string",
    "Currency": "integer",
    "OptFls": "bitstring",
    "TrgOps": "bitstring",
    "SvOptFls": "bitstring",
    "PhsMeas1": "float",
    "PhsMeas2": "float",
    "Enum": "integer",
    "Struct": "struct",
}

_NORMALIZED_BTYPE_TO_IEC_TYPE = {key.upper(): value for key, value in BTYPE_TO_IEC_TYPE.items()}


def iec_type_from_btype(btype: str) -> str:
    """把 SCL 基础类型映射为项目内部 IEC 数据类型。"""
    return _NORMALIZED_BTYPE_TO_IEC_TYPE.get(str(btype or "").strip().upper(), "unknown")


# ===== FC 到 IEC 类型推断 =====

FC_TO_IEC_TYPE: dict[str, str] = {
    "ST": "boolean",
    "MX": "float",
    "CO": "boolean",
    "SP": "string",
    "SV": "boolean",
    "CF": "float",
    "DC": "string",
    "BL": "boolean",
    "OR": "string",
    "EX": "string",
    "SX": "string",
    "SE": "string",
    "SR": "string",
    "US": "string",
    "MS": "string",
}


# ===== SCL 默认命名空间 =====

SCL_DEFAULT_NS = "http://www.iec.ch/61850/2003/SCL"
