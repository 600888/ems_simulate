"""Convert libIEC61850 MMS values to native Python values."""

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


def mms_value_to_python(mms_value, iec_type: str = IEC_TYPE_UNKNOWN) -> Any:
    """Convert a SWIG ``MmsValue`` into a JSON-serializable Python value.

    Runtime aggregate types are handled before the configured scalar type.
    Reports can contain a complete CDC structure even when the configured FCDA
    points at a leaf such as ``AnIn1.mag.f``.
    """
    if not HAS_IEC61850:
        return None

    from pyiec61850 import pyiec61850 as iec61850

    if mms_value is None:
        return None

    mms_type = None
    type_text = ""
    try:
        mms_type = iec61850.MmsValue_getType(mms_value)
    except Exception:
        pass
    try:
        type_text = str(iec61850.MmsValue_getTypeString(mms_value) or "").lower()
    except Exception:
        pass

    def is_mms_type(*names: str) -> bool:
        return any(mms_type == getattr(iec61850, name, object()) for name in names)

    # Calling a scalar accessor on an MMS structure is unsafe. Recursively
    # convert its children by their own runtime MMS types instead.
    if is_mms_type("MMS_ARRAY", "MMS_STRUCTURE") or "array" in type_text or "structure" in type_text:
        try:
            size = int(iec61850.MmsValue_getArraySize(mms_value))
            result = []
            for index in range(size):
                element = iec61850.MmsValue_getElement(mms_value, index)
                if element is not None:
                    result.append(mms_value_to_python(element, IEC_TYPE_UNKNOWN))
            return result
        except Exception:
            return _safe_mms_string(iec61850, mms_value)

    # Prefer configured IEC metadata for scalar values.
    if iec_type == IEC_TYPE_FLOAT:
        try:
            return float(iec61850.MmsValue_toFloat(mms_value))
        except Exception:
            return None
    if iec_type == IEC_TYPE_INTEGER:
        integer_accessors = (
            ("MmsValue_toUint32", "MmsValue_toInt32", "MmsValue_toInt64")
            if is_mms_type("MMS_UNSIGNED") or "unsigned" in type_text
            else ("MmsValue_toInt32", "MmsValue_toInt64", "MmsValue_toUint32")
        )
        for func_name in integer_accessors:
            func = getattr(iec61850, func_name, None)
            if func is not None:
                try:
                    return int(func(mms_value))
                except Exception:
                    pass
        return None
    if iec_type == IEC_TYPE_BOOLEAN:
        try:
            return bool(iec61850.MmsValue_getBoolean(mms_value))
        except Exception:
            return None
    if iec_type == IEC_TYPE_STRING:
        return _safe_mms_string(iec61850, mms_value)
    if iec_type == IEC_TYPE_TIMESTAMP:
        try:
            return int(iec61850.MmsValue_getUtcTimeInMs(mms_value))
        except Exception:
            return None

    # No configured type: dispatch strictly by runtime MMS type.
    try:
        if is_mms_type("MMS_FLOAT") or "float" in type_text:
            return float(iec61850.MmsValue_toFloat(mms_value))
        if is_mms_type("MMS_BOOLEAN") or "boolean" in type_text:
            return bool(iec61850.MmsValue_getBoolean(mms_value))
        if is_mms_type("MMS_UNSIGNED") or "unsigned" in type_text:
            return int(iec61850.MmsValue_toUint32(mms_value))
        if is_mms_type("MMS_INTEGER") or "integer" in type_text:
            return int(iec61850.MmsValue_toInt32(mms_value))
        if is_mms_type("MMS_BIT_STRING") or "bit-string" in type_text or "bitstring" in type_text:
            return int(iec61850.MmsValue_getBitStringAsInteger(mms_value))
        if is_mms_type("MMS_OCTET_STRING") or "octet" in type_text:
            size = int(iec61850.MmsValue_getOctetStringSize(mms_value))
            return bytes(int(iec61850.MmsValue_getOctetStringOctet(mms_value, index)) for index in range(size)).hex()
        if is_mms_type("MMS_VISIBLE_STRING", "MMS_STRING") or "string" in type_text:
            return _safe_mms_string(iec61850, mms_value)
        if is_mms_type("MMS_UTC_TIME") or "utc" in type_text:
            return int(iec61850.MmsValue_getUtcTimeInMs(mms_value))
        if is_mms_type("MMS_BINARY_TIME") or "binary-time" in type_text or "binary time" in type_text:
            return int(iec61850.MmsValue_getBinaryTimeAsUtcMs(mms_value))
        if is_mms_type("MMS_BCD") or "bcd" in type_text:
            return int(iec61850.MmsValue_toInt32(mms_value))
    except Exception:
        pass

    return _safe_mms_string(iec61850, mms_value)


def _safe_mms_string(iec61850, mms_value) -> str | None:
    """Return a readable MMS string without leaking a SWIG object repr."""
    try:
        text = str(iec61850.MmsValue_toString(mms_value) or "")
    except Exception:
        return None
    return text if text and "<Swig Object" not in text else None
