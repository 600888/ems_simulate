"""IEC 61850 MMS 值与 Python 类型转换

从 iec61850_client.py 的 _mms_value_to_python 提取，
供 Client/Server/ModelExporter 共用。
"""

from typing import Any

from ..defs.constants import (
    HAS_IEC61850,
    IEC_TYPE_BOOLEAN,
    IEC_TYPE_FLOAT,
    IEC_TYPE_INTEGER,
    IEC_TYPE_STRING,
    IEC_TYPE_TIMESTAMP,
    IEC_TYPE_UNKNOWN,
)
from ..log import log


def mms_value_to_python(mms_value, iec_type: str = IEC_TYPE_UNKNOWN) -> Any:
    """将 MmsValue 转换为 Python 原生类型

    根据 iec_type 或 MmsValue 的 MmsType 自动选择合适的读取方法。

    Args:
        mms_value: pyiec61850 MmsValue 对象
        iec_type: 期望的数据类型 (float/boolean/integer/string/timestamp/unknown)

    Returns:
        Python 原生值 (float/bool/int/str)，None 表示转换失败
    """
    if not HAS_IEC61850:
        return None

    from pyiec61850 import pyiec61850 as iec61850

    if mms_value is None:
        return None

    if not hasattr(iec61850, "MmsValue_getType"):
        return None

    # 优先按已知 iec_type 读取
    if iec_type in (IEC_TYPE_FLOAT, IEC_TYPE_INTEGER):
        try:
            return float(iec61850.MmsValue_toFloat(mms_value))
        except Exception:
            try:
                return int(str(mms_value))
            except Exception:
                return None
    elif iec_type == IEC_TYPE_BOOLEAN:
        try:
            return bool(iec61850.MmsValue_getBoolean(mms_value))
        except Exception:
            return None
    elif iec_type == IEC_TYPE_STRING:
        try:
            return str(iec61850.MmsValue_toString(mms_value))
        except Exception:
            return None
    elif iec_type == IEC_TYPE_TIMESTAMP:
        try:
            return iec61850.MmsValue_getUtcTimeInMs(mms_value)
        except Exception:
            return None

    # 未知类型: 根据 MmsType 自动探测
    try:
        mms_type = iec61850.MmsValue_getType(mms_value)
        type_str = iec61850.MmsValue_getTypeString(mms_value)

        # FLOAT 类型
        if mms_type in (iec61850.MMS_FLOAT,) or "float" in type_str.lower():
            try:
                return float(iec61850.MmsValue_toFloat(mms_value))
            except Exception:
                return str(mms_value)

        # BOOLEAN 类型
        elif mms_type in (iec61850.MMS_BOOLEAN,):
            try:
                return bool(iec61850.MmsValue_getBoolean(mms_value))
            except Exception:
                return str(mms_value)

        # INTEGER / UNSIGNED 类型
        elif mms_type in (iec61850.MMS_INTEGER, iec61850.MMS_UNSIGNED):
            try:
                return int(str(mms_value))
            except Exception:
                return str(mms_value)

        # BITSTRING 类型 (状态/控制值)
        elif mms_type in (iec61850.MMS_BITSTRING,):
            try:
                return iec61850.MmsValue_getBitStringAsInteger(mms_value)
            except Exception:
                return str(mms_value)

        # STRING 类型
        elif mms_type in (iec61850.MMS_VISIBLE_STRING, iec61850.MMS_STRING):
            try:
                return str(iec61850.MmsValue_toString(mms_value))
            except Exception:
                return str(mms_value)

        # UTC_TIME 类型
        elif mms_type in (iec61850.MMS_UTC_TIME,):
            try:
                return iec61850.MmsValue_getUtcTimeInMs(mms_value)
            except Exception:
                return str(mms_value)

        # ARRAY / STRUCTURE 类型 (递归解析)
        elif mms_type in (iec61850.MMS_ARRAY, iec61850.MMS_STRUCTURE):
            try:
                size = iec61850.MmsValue_getArraySize(mms_value)
                result = []
                for i in range(size):
                    el = iec61850.MmsValue_getElement(mms_value, i)
                    if el:
                        result.append(mms_value_to_python(el, IEC_TYPE_UNKNOWN))
                return result
            except Exception:
                return str(mms_value)

        else:
            try:
                return float(iec61850.MmsValue_toFloat(mms_value))
            except Exception:
                return str(mms_value)
    except Exception:
        try:
            return float(iec61850.MmsValue_toFloat(mms_value))
        except Exception:
            try:
                return str(mms_value)
            except Exception:
                return None
