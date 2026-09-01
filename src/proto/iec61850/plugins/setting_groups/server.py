"""Server-side IEC 61850 setting-group management."""

from __future__ import annotations

import threading
import time
from typing import Any

from ...defs.constants import HAS_IEC61850
from ...defs.mms_types import MmsType
from ...log import log

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class ServerSettingGroupsManager:
    """Manage SGCB state and FC=SG/SE values for a local IED server."""

    def __init__(self, server: Any):
        self._server = server
        self._controls: dict[str, dict[str, Any]] = {}
        self._group_values: dict[str, dict[int, dict[str, Any]]] = {}
        self._lock = threading.RLock()

    def clear(self) -> None:
        with self._lock:
            self._controls.clear()
            self._group_values.clear()

    def register(self, ld_inst: str, num_of_sg: int, act_sg: int = 1, ln_name: str = "LLN0") -> bool:
        """Create and index one SGCB for a logical device before server start."""
        num_of_sg = max(1, int(num_of_sg))
        act_sg = min(max(1, int(act_sg)), num_of_sg)
        ref = f"{ld_inst}/{ln_name}.SGCB"
        if ref in self._controls:
            return True
        parent = self._server._ln_map.get(f"{ld_inst}/{ln_name}")
        if parent is None:
            return False
        try:
            native = iec61850.SettingGroupControlBlock_create(parent, act_sg, num_of_sg)
        except Exception as exc:
            log.warning(f"创建服务端 SGCB 失败: ref={ref}, error={exc}")
            return False
        self._controls[ref] = {
            "name": "SGCB",
            "ref": ref,
            "ld": ld_inst,
            "ln": ln_name,
            "num_of_sg": num_of_sg,
            "act_sg": act_sg,
            "edit_sg": 0,
            "cnf_edit": False,
            "last_activation_time": 0,
            "reservation_time": 0,
            "native": native,
        }
        self._group_values[ref] = {}
        return True

    def load_from_scl(self, doc: Any, ied_name: str) -> None:
        """Register SettingControl definitions belonging to the selected IED."""
        for ied in getattr(doc, "ieds", []):
            if ied.name != ied_name:
                continue
            for access_point in ied.access_points:
                if not access_point.server:
                    continue
                for ld in access_point.server.ldevices:
                    if ld.ln0 and getattr(ld.ln0, "setting_control", None):
                        control = ld.ln0.setting_control
                        self.register(ld.inst, control.num_of_sg, control.act_sg, ld.ln0.ln_name)

    def discover(self) -> list[dict[str, Any]]:
        with self._lock:
            return [{key: item[key] for key in ("name", "ref", "ld", "ln")} for item in self._controls.values()]

    def get_detail(self, sgcb_ref: str) -> dict[str, Any]:
        with self._lock:
            item = self._controls.get(sgcb_ref)
            if not item:
                raise ValueError(f"SGCB 不存在: {sgcb_ref}")
            return {
                key: item[key]
                for key in (
                    "name",
                    "ref",
                    "num_of_sg",
                    "act_sg",
                    "edit_sg",
                    "cnf_edit",
                    "last_activation_time",
                    "reservation_time",
                )
            } | {"writable": True}

    def _setting_addresses(self, sgcb_ref: str) -> list[str]:
        ld_inst = sgcb_ref.split("/", 1)[0]
        return sorted(
            address
            for address, fc in self._server._point_fc.items()
            if str(fc).upper() == "SG" and address.startswith(f"{ld_inst}/")
        )

    def _current_snapshot(self, sgcb_ref: str) -> dict[str, Any]:
        return {
            address: self._server.get_point_value(address, fc="SG") for address in self._setting_addresses(sgcb_ref)
        }

    def _ensure_group(self, sgcb_ref: str, group: int) -> dict[str, Any]:
        groups = self._group_values.setdefault(sgcb_ref, {})
        if group not in groups:
            control = self._controls[sgcb_ref]
            active_values = groups.get(control["act_sg"])
            groups[group] = dict(active_values if active_values is not None else self._current_snapshot(sgcb_ref))
        return groups[group]

    def list_settings(self, sgcb_ref: str) -> list[dict[str, Any]]:
        with self._lock:
            control = self._controls.get(sgcb_ref)
            if not control:
                return []
            current = self._ensure_group(sgcb_ref, control["act_sg"])
            edit_group = control["edit_sg"] or control["act_sg"]
            edit = self._ensure_group(sgcb_ref, edit_group)
            settings = []
            for address in self._setting_addresses(sgcb_ref):
                settings.append(
                    {
                        "address": address,
                        "ref": self._server._point_refs.get(address, address),
                        "code": address.split("/", 1)[-1],
                        "description": "",
                        "unit": "",
                        "iec_type": self._server._point_iec_type.get(address, ""),
                        "mms_type": self._server._point_mms_type.get(address, MmsType.UNKNOWN.value),
                        "current_value": current.get(address),
                        "edit_value": edit.get(address),
                    }
                )
            return settings

    def select_edit_group(self, sgcb_ref: str, group: int) -> bool:
        with self._lock:
            control = self._controls.get(sgcb_ref)
            if not control or not 1 <= int(group) <= control["num_of_sg"]:
                return False
            self._ensure_group(sgcb_ref, int(group))
            control["edit_sg"] = int(group)
            control["cnf_edit"] = False
            return True

    def write_values(self, values: list[dict[str, Any]], sgcb_ref: str = "") -> list[dict[str, Any]]:
        with self._lock:
            control = self._controls.get(sgcb_ref)
            edit_group = int(control["edit_sg"]) if control else 0
            editable = self._ensure_group(sgcb_ref, edit_group) if control and edit_group else None
            valid_addresses = set(self._setting_addresses(sgcb_ref)) if control else set()
            results = []
            for item in values:
                address = str(item.get("address") or item.get("ref") or "")
                success = bool(editable is not None and address in valid_addresses)
                if success:
                    editable[address] = item.get("value")
                    control["cnf_edit"] = False
                results.append({"address": address, "success": success})
            return results

    def confirm_edit(self, sgcb_ref: str) -> bool:
        with self._lock:
            control = self._controls.get(sgcb_ref)
            if not control or not control["edit_sg"]:
                return False
            control["cnf_edit"] = True
            return True

    def activate(self, sgcb_ref: str, group: int) -> bool:
        with self._lock:
            control = self._controls.get(sgcb_ref)
            group = int(group)
            if not control or not 1 <= group <= control["num_of_sg"]:
                return False
            values = dict(self._ensure_group(sgcb_ref, group))
            if self._server._server and self._server._is_running:
                native = control.get("native")
                if native is not None:
                    try:
                        iec61850.IedServer_changeActiveSettingGroup(self._server._server, native, group)
                    except Exception as exc:
                        log.warning(f"切换服务端 SGCB 原生状态失败: ref={sgcb_ref}, error={exc}")
                        return False
                self._server.set_point_values([(address, value, "SG") for address, value in values.items()])
            control["act_sg"] = group
            control["edit_sg"] = 0
            control["cnf_edit"] = False
            control["last_activation_time"] = int(time.time() * 1000)
            return True
