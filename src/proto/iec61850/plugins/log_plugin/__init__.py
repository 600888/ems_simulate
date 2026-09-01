"""IEC 61850 Log Control Block and MMS journal client support."""

from datetime import UTC, datetime
from typing import Any

from ...core.linked_list import get_list_from_linked_list
from ...core.mms_value import mms_value_to_python
from ...core.native_calls import call_gil_safe
from ...defs.constants import HAS_IEC61850
from ...log import log

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class LogPlugin:
    """Log 插件

    管理日志控制块操作。
    """

    def __init__(self):
        """保存插件宿主引用；协议能力在 initialize 阶段装配，在 shutdown 阶段统一释放。"""
        self._connection = None
        self._initialized = False

    @property
    def name(self) -> str:
        """返回LogPlugin当前的名称。"""
        return "log"

    @property
    def available(self) -> bool:
        """返回LogPlugin当前的可用状态。"""
        return HAS_IEC61850

    def initialize(self, connection: Any, **kwargs) -> None:
        """装配依赖并开放插件能力。"""
        self._connection = connection
        self._initialized = True
        log.info("Log 插件已初始化")

    def shutdown(self) -> None:
        """停止插件任务并释放其持有的资源。"""
        self._connection = None
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

    def _read(self, object_ref: str, fc: str = "LG") -> Any:
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

    def discover(self) -> list[dict[str, Any]]:
        """Discover LCBs and read their standard attributes."""
        if not self._is_ready():
            return []
        controls: list[dict[str, Any]] = []
        for ld in self._connection.browse_logical_devices():
            try:
                with self._connection.native_operation() as conn:
                    if conn is None:
                        return controls
                    ln_result = call_gil_safe(iec61850, "IedConnection_getLogicalDeviceDirectory", conn, ld)
                ln_list, error = self._split_result(ln_result)
                if error != iec61850.IED_ERROR_OK or ln_list is None:
                    continue
                for ln in get_list_from_linked_list(ln_list):
                    ln_ref = f"{ld}/{ln}"
                    with self._connection.native_operation() as conn:
                        if conn is None:
                            return controls
                        lcb_result = call_gil_safe(
                            iec61850,
                            "IedConnection_getLogicalNodeDirectory",
                            conn,
                            ln_ref,
                            iec61850.ACSI_CLASS_LCB,
                        )
                    lcb_list, lcb_error = self._split_result(lcb_result)
                    if lcb_error != iec61850.IED_ERROR_OK or lcb_list is None:
                        continue
                    for name in get_list_from_linked_list(lcb_list):
                        ref = name if "/" in name else f"{ln_ref}.{name}"
                        controls.append(self.get_control_detail(ref, ld=ld, ln=ln))
            except Exception as exc:
                log.warning(f"发现 LCB 失败: ld={ld}, error={exc}")
        return controls

    @staticmethod
    def _attribute_ref(lcb_ref: str, attribute: str) -> str:
        return f"{lcb_ref}.{attribute}"

    @staticmethod
    def _trg_ops(value: Any) -> dict[str, bool]:
        try:
            # TrgOps is encoded as a six-bit MMS BIT STRING with a leading
            # reserved bit. MmsValue_getBitStringAsInteger therefore exposes
            # the IEC trigger mask shifted one position to the left.
            mask = int(value or 0) >> 1
        except (TypeError, ValueError):
            mask = 0
        return {
            "dchg": bool(mask & 0x01),
            "qchg": bool(mask & 0x02),
            "dupd": bool(mask & 0x04),
            "period": bool(mask & 0x08),
            "gi": bool(mask & 0x10),
        }

    def get_control_detail(self, lcb_ref: str, *, ld: str = "", ln: str = "") -> dict[str, Any]:
        log_ref = self._read(self._attribute_ref(lcb_ref, "LogRef"))
        trg_ops = self._read(self._attribute_ref(lcb_ref, "TrgOps"))
        return {
            "name": lcb_ref.rsplit(".", 1)[-1],
            "ref": lcb_ref,
            "ld": ld or lcb_ref.split("/", 1)[0],
            "ln": ln or lcb_ref.split("/", 1)[-1].split(".", 1)[0],
            "enabled": bool(self._read(self._attribute_ref(lcb_ref, "LogEna"))),
            "log_ref": log_ref or "",
            "data_set_ref": self._read(self._attribute_ref(lcb_ref, "DatSet")) or "",
            "trg_ops": self._trg_ops(trg_ops),
            "intg_period": self._read(self._attribute_ref(lcb_ref, "IntgPd")) or 0,
        }

    def set_enabled(self, lcb_ref: str, enabled: bool) -> bool:
        """Enable or disable an LCB using FC=LG."""
        if not self._is_ready():
            return False
        with self._connection.native_operation() as conn:
            if conn is None:
                return False
            result = call_gil_safe(
                iec61850,
                "IedConnection_writeBooleanValue",
                conn,
                self._attribute_ref(lcb_ref, "LogEna"),
                self._connection.get_fc_value("LG"),
                bool(enabled),
            )
        error = result[-1] if isinstance(result, (list, tuple)) else result
        return error == iec61850.IED_ERROR_OK

    @staticmethod
    def _decode_entry_id(value: Any) -> str:
        if isinstance(value, bytes):
            return value.hex()
        return str(value or "")

    @staticmethod
    def _entry_fields(entry: Any) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        variables = iec61850.MmsJournalEntry_getJournalVariables(entry)
        if not variables:
            return fields
        node = iec61850.LinkedList_getNext(variables)
        while node:
            variable = iec61850.LinkedList_getData(node)
            if variable:
                tag = str(iec61850.MmsJournalVariable_getTag(variable) or "")
                value = iec61850.MmsJournalVariable_getValue(variable)
                fields[tag] = mms_value_to_python(value) if value else None
            node = iec61850.LinkedList_getNext(node)
        return fields

    @classmethod
    def _format_entry(cls, entry: Any, log_ref: str) -> dict[str, Any]:
        timestamp_ms = int(iec61850.MmsJournalEntry_getOccurenceTime(entry) or 0)
        timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).astimezone()
        fields = cls._entry_fields(entry)
        lowered = {key.lower(): value for key, value in fields.items()}
        object_ref = next(
            (lowered[key] for key in ("dataref", "objectreference", "object_ref", "reference") if lowered.get(key)),
            "",
        )
        message = next(
            (lowered[key] for key in ("message", "description", "text", "reason") if lowered.get(key)),
            "",
        )
        service = str(lowered.get("service") or lowered.get("service-type") or "Log")
        level = str(lowered.get("severity") or lowered.get("level") or "info").lower()
        if not message:
            visible = [f"{key}={value}" for key, value in fields.items() if value is not None]
            message = ", ".join(visible[:3]) or "IEC 61850 日志记录"
        return {
            "entry_id": cls._decode_entry_id(iec61850.MmsJournalEntry_getEntryID(entry)),
            "timestamp": timestamp.isoformat(timespec="milliseconds"),
            "timestamp_ms": timestamp_ms,
            "level": level,
            "service": service,
            "object_ref": str(object_ref),
            "message": str(message),
            "source": log_ref,
            "fields": fields,
        }

    def query(self, log_ref: str, start_time_ms: int, end_time_ms: int) -> tuple[list[dict[str, Any]], bool]:
        """Query an MMS journal time range and convert it to JSON-ready entries."""
        if not self._is_ready():
            return [], False
        with self._connection.native_operation() as conn:
            if conn is None:
                return [], False
            try:
                query_result = call_gil_safe(
                    iec61850,
                    "IedConnection_queryLogByTime",
                    conn,
                    log_ref,
                    int(start_time_ms),
                    int(end_time_ms),
                    None,
                )
            except TypeError:
                query_result = call_gil_safe(
                    iec61850,
                    "IedConnection_queryLogByTime",
                    conn,
                    log_ref,
                    int(start_time_ms),
                    int(end_time_ms),
                )
        entries_list, error = self._split_result(query_result)
        if error != iec61850.IED_ERROR_OK:
            raise RuntimeError(f"查询日志失败: IED error {error}")
        entries: list[dict[str, Any]] = []
        if entries_list:
            node = iec61850.LinkedList_getNext(entries_list)
            while node:
                entry = iec61850.LinkedList_getData(node)
                if entry:
                    entries.append(self._format_entry(entry, log_ref))
                node = iec61850.LinkedList_getNext(node)
            iec61850.LinkedList_destroy(entries_list)
        entries.sort(key=lambda item: item["timestamp_ms"], reverse=True)
        more_follows = (
            bool(query_result[1]) if isinstance(query_result, (list, tuple)) and len(query_result) > 2 else False
        )
        return entries, more_follows
