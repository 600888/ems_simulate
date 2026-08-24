"""MMS client-side control of remote GOOSE control blocks."""

from __future__ import annotations

import contextlib
from typing import Any

from ...core.native_calls import call_gil_safe
from ...defs.constants import HAS_IEC61850
from ...defs.error_codes import format_ied_error
from ...log import log

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class GooseClientControl:
    """Read and write a remote GoCB through the existing MMS connection."""

    # libiec61850 ClientGooseControlBlock element mask.
    GO_ENA = 1

    @staticmethod
    def _candidate_refs(go_cb_ref: str) -> tuple[str, ...]:
        """生成控制块引用的兼容候选形式，以适配不同服务端命名习惯。"""
        if "$GO$" in go_cb_ref:
            ln_ref, cb_name = go_cb_ref.split("$GO$", 1)
        elif ".GO." in go_cb_ref:
            ln_ref, cb_name = go_cb_ref.split(".GO.", 1)
        elif "." in go_cb_ref:
            ln_ref, cb_name = go_cb_ref.rsplit(".", 1)
        else:
            return (go_cb_ref,)
        return tuple(dict.fromkeys((f"{ln_ref}.{cb_name}", f"{ln_ref}.GO.{cb_name}")))

    @staticmethod
    def _extract_error(result: Any) -> Any:
        """从 pyiec61850 的多种返回结构中提取统一错误码。"""
        return (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result

    @classmethod
    def set_go_ena(cls, connection: Any, go_cb_ref: str, enabled: bool) -> bool:
        """设置GO使能状态。"""
        if not HAS_IEC61850 or connection is None:
            return False
        native_connection = getattr(connection, "connection", None)
        if not native_connection:
            log.error(f"设置远端 GoCB GoEna 失败: MMS 连接不可用, ref={go_cb_ref}")
            return False

        mask = getattr(iec61850, "GOCB_ELEMENT_GO_ENA", cls.GO_ENA)
        last_error = None
        for candidate_ref in cls._candidate_refs(go_cb_ref):
            block = None
            try:
                block = iec61850.ClientGooseControlBlock_create(candidate_ref)
                if not block:
                    continue
                result = call_gil_safe(iec61850, "IedConnection_getGoCBValues", native_connection, candidate_ref, block)
                error = cls._extract_error(result)
                if error != iec61850.IED_ERROR_OK:
                    last_error = error
                    continue

                iec61850.ClientGooseControlBlock_setGoEna(block, enabled)
                result = call_gil_safe(iec61850, "IedConnection_setGoCBValues", native_connection, block, mask, True)
                error = cls._extract_error(result)
                if error == iec61850.IED_ERROR_OK:
                    log.info(f"远端 GoCB GoEna 已{'使能' if enabled else '禁用'}: ref={candidate_ref}")
                    return True
                last_error = error
            except Exception as exc:
                last_error = exc
            finally:
                if block is not None:
                    with contextlib.suppress(Exception):
                        iec61850.ClientGooseControlBlock_destroy(block)

        log.error(f"设置远端 GoCB GoEna 失败: ref={go_cb_ref}, enabled={enabled}, error={format_ied_error(last_error)}")
        return False
