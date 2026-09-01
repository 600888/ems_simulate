"""IEC 61850 Setting Group Control Block (SGCB) client support."""

from typing import Any

from ...core.linked_list import get_list_from_linked_list
from ...core.mms_value import mms_value_to_python
from ...core.native_calls import call_gil_safe
from ...defs.constants import HAS_IEC61850
from ...defs.mms_types import MmsType
from ...log import log

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class SettingGroupsPlugin:
    """Setting Groups 插件

    管理定值组控制块操作。
    """

    def __init__(self):
        """保存插件宿主引用；协议能力在 initialize 阶段装配，在 shutdown 阶段统一释放。"""
        self._connection = None
        self._client = None
        self._registry = None
        self._initialized = False

    @property
    def name(self) -> str:
        """返回SettingGroupsPlugin当前的名称。"""
        return "setting_groups"

    @property
    def available(self) -> bool:
        """返回SettingGroupsPlugin当前的可用状态。"""
        return HAS_IEC61850

    def initialize(self, connection: Any, **kwargs) -> None:
        """装配依赖并开放插件能力。"""
        self._connection = connection
        self._client = kwargs.get("client")
        self._registry = kwargs.get("registry")
        self._initialized = True
        log.info("SettingGroups 插件已初始化")

    def shutdown(self) -> None:
        """停止插件任务并释放其持有的资源。"""
        self._connection = None
        self._client = None
        self._registry = None
        self._initialized = False

    def _is_ready(self) -> bool:
        return bool(self._initialized and self._connection and self._connection.is_connected)

    @staticmethod
    def _split_result(result: Any) -> tuple[Any, int]:
        if isinstance(result, (list, tuple)):
            if not result:
                return None, -1
            return result[0], int(result[-1]) if len(result) > 1 else 0
        return result, 0

    def _read(self, object_ref: str, fc: str = "SP") -> Any:
        if not self._is_ready():
            return None
        with self._connection.native_operation() as conn:
            if conn is None:
                return None
            result = call_gil_safe(
                iec61850,
                "IedConnection_readObject",
                conn,
                object_ref,
                self._connection.get_fc_value(fc),
            )
        value, error = self._split_result(result)
        if error != iec61850.IED_ERROR_OK or value is None:
            return None
        try:
            return mms_value_to_python(value)
        finally:
            iec61850.MmsValue_delete(value)

    def _write_unsigned(self, object_ref: str, value: int, fc: str = "SP") -> bool:
        if not self._is_ready():
            return False
        with self._connection.native_operation() as conn:
            if conn is None:
                return False
            result = call_gil_safe(
                iec61850,
                "IedConnection_writeUnsigned32Value",
                conn,
                object_ref,
                self._connection.get_fc_value(fc),
                int(value),
            )
        error = result[-1] if isinstance(result, (list, tuple)) else result
        return error == iec61850.IED_ERROR_OK

    def _write_boolean(self, object_ref: str, value: bool, fc: str = "SP") -> bool:
        if not self._is_ready():
            return False
        with self._connection.native_operation() as conn:
            if conn is None:
                return False
            result = call_gil_safe(
                iec61850,
                "IedConnection_writeBooleanValue",
                conn,
                object_ref,
                self._connection.get_fc_value(fc),
                bool(value),
            )
        error = result[-1] if isinstance(result, (list, tuple)) else result
        return error == iec61850.IED_ERROR_OK

    def discover(self) -> list[dict[str, Any]]:
        """Discover SGCBs exposed by all logical nodes of the association."""
        if not self._is_ready():
            return []
        result: list[dict[str, Any]] = []
        for ld in self._connection.browse_logical_devices():
            try:
                with self._connection.native_operation() as conn:
                    if conn is None:
                        return result
                    ln_result = call_gil_safe(iec61850, "IedConnection_getLogicalDeviceDirectory", conn, ld)
                ln_list, error = self._split_result(ln_result)
                if error != iec61850.IED_ERROR_OK or ln_list is None:
                    continue
                lns = get_list_from_linked_list(ln_list)
                for ln in lns:
                    ln_ref = f"{ld}/{ln}"
                    with self._connection.native_operation() as conn:
                        if conn is None:
                            return result
                        sg_result = call_gil_safe(
                            iec61850,
                            "IedConnection_getLogicalNodeDirectory",
                            conn,
                            ln_ref,
                            iec61850.ACSI_CLASS_SGCB,
                        )
                    sg_list, sg_error = self._split_result(sg_result)
                    if sg_error != iec61850.IED_ERROR_OK or sg_list is None:
                        continue
                    for name in get_list_from_linked_list(sg_list):
                        ref = name if "/" in name else f"{ln_ref}.{name}"
                        result.append({"name": name.split(".")[-1], "ref": ref, "ld": ld, "ln": ln})
            except Exception as exc:
                log.warning(f"发现 SGCB 失败: ld={ld}, error={exc}")
        return result

    @staticmethod
    def _attribute_ref(sgcb_ref: str, attribute: str) -> str:
        return f"{sgcb_ref}.{attribute}"

    def get_detail(self, sgcb_ref: str) -> dict[str, Any]:
        """Read the standard SGCB state attributes."""
        detail = {
            "ref": sgcb_ref,
            "name": sgcb_ref.rsplit(".", 1)[-1],
            "num_of_sg": self._read(self._attribute_ref(sgcb_ref, "NumOfSG")),
            "act_sg": self._read(self._attribute_ref(sgcb_ref, "ActSG")),
            "edit_sg": self._read(self._attribute_ref(sgcb_ref, "EditSG")),
            "cnf_edit": self._read(self._attribute_ref(sgcb_ref, "CnfEdit")),
            "last_activation_time": self._read(self._attribute_ref(sgcb_ref, "LActTm")),
            "reservation_time": self._read(self._attribute_ref(sgcb_ref, "ResvTms")),
        }
        detail["writable"] = self._is_ready()
        return detail

    def list_settings(self, sgcb_ref: str) -> list[dict[str, Any]]:
        """Return FC=SG values belonging to the SGCB logical device/node."""
        if not self._client:
            return []
        ld_ref = sgcb_ref.split("/", 1)[0]
        model = getattr(self._client, "model", None)
        point_refs = getattr(model, "point_refs", {}) if model is not None else {}
        settings: list[dict[str, Any]] = []
        for address, info in point_refs.items():
            if str(info.get("fc", "")).upper() != "SG":
                continue
            ref = str(info.get("ref") or address)
            if not (ref.startswith(f"{ld_ref}/") or str(address).startswith(f"{ld_ref}/")):
                continue
            current_value = self._client.read_point(address, fc="SG")
            edit_value = self._client.read_point(address, fc="SE")
            settings.append(
                {
                    "address": address,
                    "ref": ref,
                    "code": info.get("code") or ref.split("/", 1)[-1],
                    "description": info.get("description") or "",
                    "unit": info.get("unit") or "",
                    "iec_type": info.get("iec_type") or "",
                    "mms_type": info.get("mms_type") or MmsType.UNKNOWN.value,
                    "current_value": current_value,
                    "edit_value": edit_value,
                }
            )
        return sorted(settings, key=lambda item: item["ref"])

    def select_edit_group(self, sgcb_ref: str, group: int) -> bool:
        """Select the group whose FC=SE values will be read or written."""
        return self._write_unsigned(self._attribute_ref(sgcb_ref, "EditSG"), group)

    def write_values(self, values: list[dict[str, Any]], sgcb_ref: str = "") -> list[dict[str, Any]]:
        """Write a batch of editable setting values using FC=SE."""
        results: list[dict[str, Any]] = []
        for item in values:
            address = str(item.get("address") or item.get("ref") or "")
            success = bool(address and self._client and self._client.write_point(address, item.get("value"), fc="SE"))
            results.append({"address": address, "success": success})
        return results

    def confirm_edit(self, sgcb_ref: str) -> bool:
        """Commit the currently selected edit group."""
        return self._write_boolean(self._attribute_ref(sgcb_ref, "CnfEdit"), True)

    def activate(self, sgcb_ref: str, group: int) -> bool:
        """Activate a confirmed setting group."""
        return self._write_unsigned(self._attribute_ref(sgcb_ref, "ActSG"), group)
