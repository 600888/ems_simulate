"""Server-side IEC 61850 log-control and local journal management."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
import threading
import time
from typing import Any

from ...defs.constants import HAS_IEC61850
from ...log import log

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class ServerLogManager:
    """Own local LCB definitions and a bounded journal for a server device."""

    def __init__(self, server: Any, max_entries: int = 10000):
        self._server = server
        self._controls: dict[str, dict[str, Any]] = {}
        self._logs: dict[str, deque[dict[str, Any]]] = {}
        self._sequence = 0
        self._max_entries = max_entries
        self._lock = threading.RLock()

    def clear(self) -> None:
        with self._lock:
            self._controls.clear()
            self._logs.clear()
            self._sequence = 0

    @staticmethod
    def _trigger_mask(trg_ops: Any) -> int:
        return (
            (0x01 if getattr(trg_ops, "dchg", False) else 0)
            | (0x02 if getattr(trg_ops, "qchg", False) else 0)
            | (0x04 if getattr(trg_ops, "dupd", False) else 0)
            | (0x08 if getattr(trg_ops, "period", False) else 0)
            | (0x10 if getattr(trg_ops, "gi", False) else 0)
        )

    @staticmethod
    def _trigger_map(mask: int) -> dict[str, bool]:
        return {
            "dchg": bool(mask & 0x01),
            "qchg": bool(mask & 0x02),
            "dupd": bool(mask & 0x04),
            "period": bool(mask & 0x08),
            "gi": bool(mask & 0x10),
        }

    def register_log(self, ld_inst: str, ln_name: str, name: str) -> str:
        log_ref = f"{ld_inst}/{ln_name}${name}"
        if log_ref in self._logs:
            return log_ref
        parent = self._server._ln_map.get(f"{ld_inst}/{ln_name}")
        if parent is not None:
            try:
                iec61850.Log_create(name, parent)
            except Exception as exc:
                log.warning(f"创建服务端 Log 失败: ref={log_ref}, error={exc}")
        self._logs[log_ref] = deque(maxlen=self._max_entries)
        return log_ref

    def register_control(
        self,
        ld_inst: str,
        ln_name: str,
        name: str,
        data_set: str,
        log_name: str,
        trg_ops: Any,
        intg_period: int,
        enabled: bool,
        reason_code: bool,
    ) -> bool:
        ref = f"{ld_inst}/{ln_name}.{name}"
        log_ref = self.register_log(ld_inst, ln_name, log_name)
        data_set_ref = data_set if "/" in data_set else f"{ld_inst}/{ln_name}${data_set}"
        native_data_set_name = data_set_ref.rsplit("$", 1)[-1]
        mask = self._trigger_mask(trg_ops)
        parent = self._server._ln_map.get(f"{ld_inst}/{ln_name}")
        native = None
        if parent is not None:
            try:
                native = iec61850.LogControlBlock_create(
                    name,
                    parent,
                    native_data_set_name,
                    log_ref,
                    mask,
                    int(intg_period),
                    bool(enabled),
                    bool(reason_code),
                )
            except Exception as exc:
                log.warning(f"创建服务端 LCB 失败: ref={ref}, error={exc}")
                return False
        self._controls[ref] = {
            "name": name,
            "ref": ref,
            "ld": ld_inst,
            "ln": ln_name,
            "enabled": bool(enabled),
            "log_ref": log_ref,
            "data_set_ref": data_set_ref,
            "trg_ops": self._trigger_map(mask),
            "intg_period": int(intg_period),
            "reason_code": bool(reason_code),
            "native": native,
        }
        return True

    def load_from_scl(self, doc: Any, ied_name: str) -> None:
        for ied in getattr(doc, "ieds", []):
            if ied.name != ied_name:
                continue
            for access_point in ied.access_points:
                if not access_point.server:
                    continue
                for ld in access_point.server.ldevices:
                    for ln in ([ld.ln0] + ld.lns) if ld.ln0 else ld.lns:
                        for item in getattr(ln, "logs", []):
                            self.register_log(ld.inst, ln.ln_name, item.name)
                        for item in getattr(ln, "log_controls", []):
                            self.register_control(
                                ld.inst,
                                ln.ln_name,
                                item.name,
                                item.dat_set,
                                item.log_name,
                                item.trg_ops,
                                item.intg_period,
                                item.log_ena,
                                item.reason_code,
                            )

    def discover(self) -> list[dict[str, Any]]:
        with self._lock:
            return [{key: value for key, value in item.items() if key != "native"} for item in self._controls.values()]

    def set_enabled(self, lcb_ref: str, enabled: bool) -> bool:
        with self._lock:
            item = self._controls.get(lcb_ref)
            if not item:
                return False
            item["enabled"] = bool(enabled)
            native = item.get("native")
            if native is not None and hasattr(native, "logEna"):
                native.logEna = bool(enabled)
            return True

    def record(
        self,
        object_ref: str,
        value: Any,
        *,
        service: str = "DataChange",
        level: str = "info",
        message: str = "",
    ) -> None:
        now_ms = int(time.time() * 1000)
        timestamp = datetime.fromtimestamp(now_ms / 1000, tz=UTC).astimezone().isoformat(timespec="milliseconds")
        with self._lock:
            for control in self._controls.values():
                if not control["enabled"]:
                    continue
                self._sequence += 1
                entry = {
                    "entry_id": f"{now_ms:013d}-{self._sequence:06d}",
                    "timestamp": timestamp,
                    "timestamp_ms": now_ms,
                    "level": level,
                    "service": service,
                    "object_ref": object_ref,
                    "message": message or f"{object_ref} 更新为 {value}",
                    "source": control["log_ref"],
                    "fields": {"value": value, "reason": "data-change"},
                }
                self._logs.setdefault(control["log_ref"], deque(maxlen=self._max_entries)).append(entry)

    def query(self, log_ref: str, start_time_ms: int, end_time_ms: int) -> tuple[list[dict[str, Any]], bool]:
        with self._lock:
            entries = [
                dict(item)
                for item in self._logs.get(log_ref, ())
                if int(start_time_ms) <= item["timestamp_ms"] <= int(end_time_ms)
            ]
        entries.sort(key=lambda item: item["timestamp_ms"], reverse=True)
        return entries, False
