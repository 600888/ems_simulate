"""报告回调处理模块

封装 C 回调注册/注销，ClientReport 解析与数据缓存。
回调在 libIEC61850 的接收线程中执行，使用 queue 异步处理避免阻塞。
"""

from collections.abc import Callable
import contextlib
from dataclasses import dataclass, field
import datetime
import threading
from typing import Any

from ...core.mms_value import mms_value_to_python
from ...defs.constants import HAS_IEC61850
from ...defs.types import ReportDataEntry
from ...log import log

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


# 全局回调映射表: rcb_ref -> callback_info
# C 回调无法绑定到实例方法，需通过静态函数 + 全局字典分发
_CALLBACK_REGISTRY: dict[str, "_CallbackInfo"] = {}
_CALLBACK_LOCK = threading.Lock()
MAX_REPORT_VALUES_PER_ENTRY = 512


@dataclass
class _CallbackInfo:
    """回调注册信息"""

    rcb_ref: str
    handler: Any = None  # _PyRCBHandler 实例 (保持引用防 GC)
    subscriber: Any = None  # RCBSubscriber 实例 (保持引用防 GC)
    on_report: Callable | None = None  # Python 回调函数
    data_cache: list[ReportDataEntry] = field(default_factory=list)
    max_cache: int = 1000
    enabled_at: str = ""
    mms_ref: str = ""


def _normalize_ref(rcb_ref: str, rcb_type: str = "") -> str:
    """Normalize an RCB ref for report handler registration.

    libIEC61850 uses dot FC form for IedConnection_installReportHandler,
    e.g. LD/LLN0.RP.EventsRCB. For indexed URCB instances, RCB services use
    EventsRCB01, while the report handler is registered on the base EventsRCB.
    """
    if not rcb_ref or "/" not in rcb_ref:
        return rcb_ref

    ref = rcb_ref.replace("$", ".")
    if "." not in ref:
        return ref

    ln_part, name = ref.rsplit(".", 1)
    parts = ln_part.split(".")
    if len(parts) >= 2 and parts[-1] in ("BR", "RP"):
        fc = parts[-1]
        ln_only = ".".join(parts[:-1])
    else:
        ln_only = ln_part
        normalized_type = (rcb_type or "").upper()
        if normalized_type == "BRCB":
            fc = "BR"
        elif normalized_type == "URCB":
            fc = "RP"
        else:
            low = name.lower()
            fc = "RP" if (low.startswith("rp") or low.startswith("urcb")) else "BR"

    base_name = _strip_report_instance_suffix(name)
    return f"{ln_only}.{fc}.{base_name}"


def _strip_report_instance_suffix(name: str) -> str:
    """Strip RptEnabled instance suffix like 01 from report handler refs."""
    if len(name) > 2 and name[-2:].isdigit():
        return name[:-2]
    return name


class ReportCallbackHandler:
    """报告回调管理器

    管理 C 级别报告回调的注册/注销，以及报告数据的解析与缓存。
    线程安全：C 回调在 libIEC61850 的接收线程中执行，
    通过 _CALLBACK_LOCK 保护注册表和缓存。
    """

    @staticmethod
    def install(
        connection,
        rcb_ref: str,
        on_report: Callable[[ReportDataEntry], None] | None = None,
        max_cache: int = 1000,
        rpt_id: str = "",
        rcb_type: str = "",
    ) -> bool:
        """安装报告回调

        Args:
            connection: Iec61850Connection 实例
            rcb_ref: RCB 引用路径
            on_report: 可选 Python 回调，收到报告时调用
            max_cache: 最大缓存条数
            rpt_id: 报告 ID (可空, 空表示接受任意)

        Returns:
            bool 是否成功
        """
        if not HAS_IEC61850:
            return False
        conn = connection.connection
        if not conn:
            log.warning(f"安装报告回调失败: 连接不可用, ref={rcb_ref}")
            return False

        # 如果已注册，先注销
        # 注意：不能在锁内调用 uninstall，因为 uninstall 需要在锁外调用 C 层注销
        with _CALLBACK_LOCK:
            already_registered = rcb_ref in _CALLBACK_REGISTRY
        if already_registered:
            ReportCallbackHandler.uninstall(connection, rcb_ref)

        with _CALLBACK_LOCK:
            if not (hasattr(iec61850, "RCBHandler") and hasattr(iec61850, "RCBSubscriber")):
                log.warning("pyiec61850 不支持 RCBHandler/RCBSubscriber, 无法安装报告回调")
                return False

            try:
                nref = _normalize_ref(rcb_ref, rcb_type)
                handler = _PyRCBHandler(rcb_ref)
                subscriber = iec61850.RCBSubscriber()
                subscriber.setIedConnection(conn)
                subscriber.setRcbReference(nref)
                subscriber.setRcbRptId(rpt_id or "")
                subscriber.setEventHandler(handler)
                if not subscriber.subscribe():
                    log.warning(f"订阅报告失败: ref={nref}")
                    return False

                _CALLBACK_REGISTRY[rcb_ref] = _CallbackInfo(
                    rcb_ref=rcb_ref,
                    handler=handler,
                    subscriber=subscriber,
                    on_report=on_report,
                    max_cache=max_cache,
                    enabled_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    mms_ref=nref,
                )
                log.info(f"报告回调已安装: {rcb_ref} (mms_ref={nref})")
                return True
            except Exception as e:
                log.error(f"安装报告回调异常: {rcb_ref}, {e}")
                return False

    @staticmethod
    def uninstall(connection, rcb_ref: str) -> bool:
        """注销报告回调

        RCBSubscriber 没有 unsubscribe 方法，正确的注销顺序:
        1. 锁内从注册表移除，阻止 _dispatch_report 继续分发
        2. 锁外调用 subscriber.deleteEventHandler() 断开 SWIG director 链接，
           使 C++ 接收线程不再回调 Python trigger()
        3. 调用 IedConnection_uninstallReportHandler 按 rcbReference 注销 C++ 侧订阅，
           确保再次 subscribe() 时不会报 "already registered"
        4. 释放 subscriber/handler 的 Python 引用，让 GC 销毁 C++ 对象

        注意: 不能在持有 _CALLBACK_LOCK 时调用 C 层操作，
        否则与 _dispatch_report 中的锁形成死锁导致程序崩溃。
        """
        if not HAS_IEC61850:
            return False
        conn = connection.connection
        if not conn:
            return False

        # 1. 锁内从注册表移除，并取出 subscriber/handler 引用
        #    这样 _dispatch_report 不再分发该 RCB 的报告
        with _CALLBACK_LOCK:
            if rcb_ref not in _CALLBACK_REGISTRY:
                return True
            info = _CALLBACK_REGISTRY.pop(rcb_ref)

        subscriber = info.subscriber
        handler = info.handler
        nref = info.mms_ref or _normalize_ref(rcb_ref)

        # 2. 锁外断开 SWIG director 链接 (C++ 不再回调 Python)
        if subscriber is not None:
            try:
                subscriber.deleteEventHandler()
            except Exception as e:
                log.debug(f"deleteEventHandler 异常 (非致命): {rcb_ref}, {e}")

        # 3. 按 rcbReference 注销 C++ 侧订阅记录 (确保可重新订阅)
        try:
            iec61850.IedConnection_uninstallReportHandler(conn, nref)
        except Exception as e:
            log.debug(f"uninstallReportHandler 异常 (非致命): {rcb_ref}, {e}")

        # 4. 释放 Python 引用，让 GC 回收 C++ 对象
        info.subscriber = None
        info.handler = None

        # 防止 SWIG 在 C++ 已释放后再次调用析构 (参考 GOOSE thisown=0)
        if handler is not None and hasattr(handler, "thisown"):
            try:
                handler.thisown = 0
            except Exception:
                pass

        log.info(f"报告回调已注销: {rcb_ref}")
        return True

    @staticmethod
    def get_cache(rcb_ref: str) -> list[dict[str, Any]]:
        """获取指定 RCB 的缓存报告数据"""
        with _CALLBACK_LOCK:
            info = _CALLBACK_REGISTRY.get(rcb_ref)
            if not info:
                return []
            return [ReportCallbackHandler._entry_to_dict(entry) for entry in info.data_cache]

    @staticmethod
    def clear_cache(rcb_ref: str) -> None:
        """清除指定 RCB 的缓存"""
        with _CALLBACK_LOCK:
            info = _CALLBACK_REGISTRY.get(rcb_ref)
            if info:
                info.data_cache.clear()

    @staticmethod
    def is_active(rcb_ref: str) -> bool:
        """检查指定 RCB 是否有活跃回调"""
        with _CALLBACK_LOCK:
            return rcb_ref in _CALLBACK_REGISTRY

    @staticmethod
    def get_active_rcbs() -> list[dict[str, Any]]:
        """获取所有活跃回调信息"""
        with _CALLBACK_LOCK:
            return [
                {
                    "rcb_ref": info.rcb_ref,
                    "enabled_since": info.enabled_at,
                    "cache_size": len(info.data_cache),
                }
                for info in _CALLBACK_REGISTRY.values()
            ]

    @staticmethod
    def shutdown_all(connection) -> None:
        """关闭所有回调（插件关闭时调用）

        采用与 uninstall 相同的清理模式:
        1. 锁内清空注册表
        2. 锁外逐个 deleteEventHandler 断开 director 链 + uninstallReportHandler 注销 C++ 订阅
        3. 释放引用，防止 SWIG 重复析构
        """
        conn = connection.connection if connection else None

        # 1. 锁内取出所有 rcb_ref 并清空注册表
        with _CALLBACK_LOCK:
            refs = list(_CALLBACK_REGISTRY.keys())
            infos = [_CALLBACK_REGISTRY.pop(ref) for ref in refs]

        # 2. 锁外逐个清理
        for ref, info in zip(refs, infos, strict=True):
            subscriber = info.subscriber
            handler = info.handler
            if subscriber is not None:
                try:
                    subscriber.deleteEventHandler()
                except Exception:
                    pass
            if conn is not None:
                try:
                    iec61850.IedConnection_uninstallReportHandler(conn, info.mms_ref or _normalize_ref(ref))
                except Exception:
                    pass
            # 防止 SWIG 重复析构
            if handler is not None and hasattr(handler, "thisown"):
                try:
                    handler.thisown = 0
                except Exception:
                    pass

        # 3. 释放引用
        for info in infos:
            info.subscriber = None
            info.handler = None
        log.info("所有报告回调已关闭")

    @staticmethod
    def _entry_to_dict(entry: ReportDataEntry) -> dict[str, Any]:
        """将 ReportDataEntry 转为字典"""
        return {
            "seq_num": entry.seq_num,
            "time_stamp": entry.time_stamp,
            "reason_codes": entry.reason_codes,
            "data_values": entry.data_values,
            "entry_id": entry.entry_id.hex() if entry.entry_id else None,
            "conf_rev": entry.conf_rev,
            "data_set": entry.data_set,
            "rpt_id": entry.rpt_id,
            "received_at": entry.received_at,
        }


def _dispatch_report(rcb_ref: str, report) -> None:
    """解析并分发一条报告 (由 _PyRCBHandler.trigger 调用)

    注意: 不能在持有 _CALLBACK_LOCK 时做耗时的 C 层解析，
    否则 uninstall 中的 IedConnection_uninstallReportHandler 会等待
    接收线程完成，而接收线程持锁解析报告时 C 层对象可能已被销毁，
    导致段错误崩溃。
    """
    log.info(f"_dispatch_report 进入: rcb_ref={rcb_ref}, report={report}")

    # 1. 锁内快速检查是否已注册，取出 on_report 回调
    with _CALLBACK_LOCK:
        info = _CALLBACK_REGISTRY.get(rcb_ref)
        if not info:
            log.warning(
                f"_dispatch_report: rcb_ref={rcb_ref} 未在注册表中找到, "
                f"当前注册表 keys={list(_CALLBACK_REGISTRY.keys())}"
            )
            return
        on_report = info.on_report

    # 2. 锁外解析报告 (耗时 C 层操作，不持锁)
    entry = _parse_client_report(report, rcb_ref)
    if entry is None:
        log.warning(f"_dispatch_report: 解析报告失败返回 None, rcb_ref={rcb_ref}")
        return

    log.info(
        f"_dispatch_report: 解析成功, rcb_ref={rcb_ref}, "
        f"seq_num={entry.seq_num}, data_values_count={len(entry.data_values)}"
    )

    # 3. 锁内写入缓存
    with _CALLBACK_LOCK:
        info = _CALLBACK_REGISTRY.get(rcb_ref)
        if not info:
            log.warning(f"_dispatch_report: 写缓存时 rcb_ref={rcb_ref} 已被注销")
            return
        info.data_cache.append(entry)
        if len(info.data_cache) > info.max_cache:
            info.data_cache.pop(0)
        log.info(f"_dispatch_report: 已写入缓存, rcb_ref={rcb_ref}, cache_size={len(info.data_cache)}")

    # 4. 锁外调用用户回调
    if on_report:
        try:
            on_report(entry)
        except Exception as cb_err:
            log.error(f"报告回调函数异常: {rcb_ref}, {cb_err}")


if HAS_IEC61850 and hasattr(iec61850, "RCBHandler"):

    class _PyRCBHandler(iec61850.RCBHandler):
        """SWIG director 子类, C++ 收到报告时回调 trigger()"""

        def __init__(self, rcb_ref: str):
            super().__init__()
            self._rcb_ref = rcb_ref

        def trigger(self):
            log.info(f"RCBHandler.trigger 被调用: rcb_ref={self._rcb_ref}")
            try:
                cr = self._client_report
                log.info(f"RCBHandler.trigger report: rcb_ref={self._rcb_ref}, report={cr}")
                _dispatch_report(self._rcb_ref, cr)
            except Exception as e:
                log.error(f"RCBHandler.trigger 异常: {self._rcb_ref}, {e}", exc_info=True)
else:

    class _PyRCBHandler:  # 占位, 不会被使用
        def __init__(self, rcb_ref: str):
            self._rcb_ref = rcb_ref


def _parse_client_report(report, rcb_ref: str) -> ReportDataEntry | None:
    """Parse ClientReport into a cacheable ReportDataEntry.

    pyiec61850-ng 1.6.1.3 exposes ClientReport_getDataSetValues,
    ClientReport_getDataSetName, and ClientReport_getReasonForInclusion.
    Older wrapper names are tried as fallbacks for compatibility.
    """
    try:
        entry = ReportDataEntry()

        try:
            rpt_id = iec61850.ClientReport_getRptId(report)
            if rpt_id:
                entry.rpt_id = str(rpt_id)
        except Exception:
            pass

        for func_name in ("ClientReport_getDataSetName", "ClientReport_getDataSet"):
            func = getattr(iec61850, func_name, None)
            if not func:
                continue
            try:
                ds = func(report)
                if ds:
                    entry.data_set = str(ds)
                    break
            except Exception:
                pass

        with contextlib.suppress(Exception):
            entry.conf_rev = int(iec61850.ClientReport_getConfRev(report))

        for func_name in ("ClientReport_getEntryId", "ClientReport_getEntryID"):
            func = getattr(iec61850, func_name, None)
            if not func:
                continue
            try:
                eid = func(report)
                if eid:
                    entry.entry_id = bytes(eid)
                    break
            except Exception:
                pass

        with contextlib.suppress(Exception):
            entry.seq_num = int(iec61850.ClientReport_getSeqNum(report))

        for func_name in ("ClientReport_getTimestamp", "ClientReport_getTimeOfEntry"):
            func = getattr(iec61850, func_name, None)
            if not func:
                continue
            try:
                time_ms = func(report)
                if time_ms and int(time_ms) > 0:
                    entry.time_stamp = datetime.datetime.fromtimestamp(int(time_ms) / 1000.0).strftime(
                        "%Y-%m-%d %H:%M:%S.%f"
                    )[:-3]
                    break
            except Exception:
                pass

        entry.received_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        values = None
        for func_name in ("ClientReport_getDataSetValues", "ClientReport_getValues"):
            func = getattr(iec61850, func_name, None)
            if not func:
                continue
            try:
                values = func(report)
                if values:
                    break
            except Exception:
                values = None

        if values:
            array_size = 0
            with contextlib.suppress(Exception):
                array_size = int(iec61850.MmsValue_getArraySize(values))

            if array_size > MAX_REPORT_VALUES_PER_ENTRY:
                log.warning(f"Report has {array_size} values, parsing first {MAX_REPORT_VALUES_PER_ENTRY}: {rcb_ref}")
            parse_count = min(array_size, MAX_REPORT_VALUES_PER_ENTRY)

            for i in range(parse_count):
                try:
                    element = iec61850.MmsValue_getElement(values, i)
                except Exception:
                    element = None
                if element is None:
                    continue

                reason_str = _get_reason_for_inclusion(report, i)
                ref_key = _get_data_reference(report, i) or f"data[{i}]"

                entry.data_values[ref_key] = mms_value_to_python(element)
                entry.reason_codes[ref_key] = reason_str

            if array_size > parse_count:
                entry.data_values["__truncated__"] = f"{array_size - parse_count} values omitted"
                entry.reason_codes["__truncated__"] = "local-limit"

        return entry
    except Exception as e:
        log.error(f"parse ClientReport failed: {rcb_ref}, {e}")
        return None


def _get_reason_for_inclusion(report, index: int) -> str:
    try:
        if hasattr(iec61850, "ClientReport_getReasonForInclusion"):
            reason = iec61850.ClientReport_getReasonForInclusion(report, index)
            if hasattr(iec61850, "ReasonForInclusion_getValueAsString"):
                reason_text = iec61850.ReasonForInclusion_getValueAsString(reason)
                if reason_text:
                    return str(reason_text)
            reason_value = int(reason)
            reason_map = {
                1: "data-change",
                2: "quality-change",
                4: "data-update",
                8: "integrity",
                16: "gi",
            }
            return reason_map.get(reason_value, f"code={reason_value}")
    except Exception:
        pass
    return "unknown"


def _get_data_reference(report, index: int) -> str:
    try:
        if hasattr(iec61850, "ClientReport_getDataReference"):
            ref = iec61850.ClientReport_getDataReference(report, index)
            if ref:
                return str(ref)
    except Exception:
        pass
    return ""
