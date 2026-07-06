"""IEC 61850 DataSet 成员目录的唯一原生解析实现。"""

from __future__ import annotations

import contextlib
from typing import Any

from ...core.native_calls import call_gil_safe
from ...defs.address import infer_fc_from_address, infer_iec_type_from_address
from ...defs.constants import IEC_TYPE_UNKNOWN
from ...log import log
from .catalog import normalize_point_ref, strip_fc_suffix


def browse_dataset_members(native: Any, conn: Any, dataset_ref: str) -> list[dict[str, Any]]:
    """读取并规范化一个 DataSet 的成员目录。"""
    # pyiec61850-ng 的 isDeletable 仍是原生 bool* 参数，且没有导出可用的
    # SWIG bool 指针构造器。官方 C API 允许在不需要该属性时传 NULL。
    # ctypes.c_bool 与 SWIG 指针不兼容，传入它只会在每个 DataSet 上抛出异常。
    try:
        result = call_gil_safe(native, "IedConnection_getDataSetDirectory", conn, dataset_ref, None)
    except Exception:
        return []
    if result is None:
        return []

    directory = result[0] if isinstance(result, (list, tuple)) else result
    error = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else 0
    if error != native.IED_ERROR_OK or directory is None:
        return []

    linked_list = getattr(directory, "fcdas", None) or directory
    members: list[dict[str, Any]] = []
    try:
        node = native.LinkedList_getNext(linked_list)
        index = 0
        while node:
            entry = None
            with contextlib.suppress(Exception):
                entry = native.LinkedList_getData(node)
            member = _extract_member(native, entry, index)
            if member is not None:
                members.append(member)
                index += 1
            node = native.LinkedList_getNext(node)
    finally:
        with contextlib.suppress(Exception):
            native.LinkedList_destroy(linked_list)
    return members


def _extract_member(native: Any, entry: Any, index: int) -> dict[str, Any] | None:
    """从 DataSetEntry 对象或字符串指针中安全提取 FCDA 信息。"""
    if entry is None:
        return None

    ld_name = _first_attr(entry, "logicalDeviceName", "ldName", "deviceName", "LogicalDeviceName")
    variable_name = _first_attr(entry, "variableName", "varName", "VariableName")
    component_name = _first_attr(entry, "componentName", "compName", "ComponentName")
    entry_index = _integer_attr(entry, "index")

    ref = ""
    if variable_name:
        ref = f"{ld_name}/{variable_name}" if ld_name else variable_name
        if entry_index > 0:
            ref = f"{ref}[{entry_index}]"
        if component_name:
            ref = f"{ref}.{component_name}"
    if not ref:
        ref = _entry_to_string(native, entry)
    if not ref or "/" not in ref:
        log.debug(f"DataSet member directory entry cannot be decoded: index={index}, type={type(entry).__name__}")
        return None

    cleaned, suffix_fc = strip_fc_suffix(ref)
    normalized = normalize_point_ref(cleaned)
    fc = suffix_fc or infer_fc_from_address(normalized) or ""
    return {
        "ref": normalized,
        "fc": fc,
        "iec_type": infer_iec_type_from_address(normalized) or IEC_TYPE_UNKNOWN,
        "mms_type": "MMS_UNKNOWN",
        "index": index,
    }


def _first_attr(entry: Any, *names: str) -> str:
    """按不同绑定版本可能使用的属性名依次取第一个非空值。"""
    for name in names:
        with contextlib.suppress(Exception):
            value = getattr(entry, name, "")
            if value:
                return str(value)
    return ""


def _integer_attr(entry: Any, name: str) -> int:
    """安全读取整型属性，绑定未暴露时返回零。"""
    with contextlib.suppress(Exception):
        return int(getattr(entry, name, 0) or 0)
    return 0


def _entry_to_string(native: Any, entry: Any) -> str:
    """在结构化字段不可用时，将原生目录项回退转换为字符串。"""
    with contextlib.suppress(Exception):
        value = native.toCharP(entry)
        if value:
            return str(value)
    with contextlib.suppress(Exception):
        value = str(entry)
        if value and value != "None" and not value.startswith("<"):
            return value
    return ""
