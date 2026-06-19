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


def _normalize_ref(rcb_ref: str) -> str:
    """规范化 RCB 引用, 按名称前缀插入 FC 段 (.RP./.BR.)

    rp*/urcb* -> .RP. (非缓冲); 其余 -> .BR. (缓冲)。
    已含 FC 段则原样返回。
    """
    if not rcb_ref or "." not in rcb_ref or "/" not in rcb_ref:
        return rcb_ref
    ln_part, name = rcb_ref.rsplit(".", 1)
    if name in ("BR", "RP"):
        return rcb_ref
    low = name.lower()
    fc = "RP" if (low.startswith("rp") or low.startswith("urcb")) else "BR"
    return f"{ln_part}.{fc}.{name}"


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

        # 如果已注册，先注销 (不能在锁内调用 uninstall，因为 uninstall 需要在锁外
        # 调用 C 层注销以避免死锁)
        with _CALLBACK_LOCK:
            already_registered = rcb_ref in _CALLBACK_REGISTRY
        if already_registered:
            ReportCallbackHandler.uninstall(connection, rcb_ref)

        with _CALLBACK_LOCK:
            if not (hasattr(iec61850, "RCBHandler") and hasattr(iec61850, "RCBSubscriber")):
                log.warning("pyiec61850 不支持 RCBHandler/RCBSubscriber, 无法安装报告回调")
                return False

            try:
                nref = _normalize_ref(rcb_ref)
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
                )
                log.info(f"报告回调已安装: {rcb_ref}")
                return True
            except Exception as e:
                log.error(f"安装报告回调异常: {rcb_ref}, {e}")
                return False

    @staticmethod
    def uninstall(connection, rcb_ref: str) -> bool:
        """注销报告回调

        注意: IedConnection_uninstallReportHandler 是同步调用，会等待接收线程
        完成当前回调。不能在持有 _CALLBACK_LOCK 时调用，否则与 _dispatch_report
        中的锁形成死锁导致程序崩溃。
        """
        if not HAS_IEC61850:
            return False
        conn = connection.connection
        if not conn:
            return False

        # 1. 先在锁内从注册表移除，并取出 subscriber/handler 引用
        #    这样 _dispatch_report 不再分发该 RCB 的报告
        with _CALLBACK_LOCK:
            if rcb_ref not in _CALLBACK_REGISTRY:
                return True
            info = _CALLBACK_REGISTRY.pop(rcb_ref)

        # 2. 在锁外调用 C 层注销 (同步等待接收线程完成当前回调)
        try:
            iec61850.IedConnection_uninstallReportHandler(conn, _normalize_ref(rcb_ref))
        except Exception as e:
            log.debug(f"注销报告回调异常 (非致命): {rcb_ref}, {e}")

        # 3. 释放 subscriber/handler 引用 (C 层注销完成后才安全释放)
        info.subscriber = None
        info.handler = None
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

        同样不能在持有 _CALLBACK_LOCK 时调用 C 层注销，避免死锁。
        """
        # 1. 锁内取出所有 rcb_ref 并清空注册表
        with _CALLBACK_LOCK:
            refs = list(_CALLBACK_REGISTRY.keys())
            infos = [_CALLBACK_REGISTRY.pop(ref) for ref in refs]

        # 2. 锁外逐个调用 C 层注销
        for ref in refs:
            try:
                if connection and connection.connection:
                    iec61850.IedConnection_uninstallReportHandler(connection.connection, _normalize_ref(ref))
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
    # 1. 锁内快速检查是否已注册，取出 on_report 回调
    with _CALLBACK_LOCK:
        info = _CALLBACK_REGISTRY.get(rcb_ref)
        if not info:
            return
        on_report = info.on_report

    # 2. 锁外解析报告 (耗时 C 层操作，不持锁)
    entry = _parse_client_report(report, rcb_ref)
    if entry is None:
        return

    # 3. 锁内写入缓存
    with _CALLBACK_LOCK:
        info = _CALLBACK_REGISTRY.get(rcb_ref)
        if not info:
            return
        info.data_cache.append(entry)
        if len(info.data_cache) > info.max_cache:
            info.data_cache.pop(0)

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
            try:
                _dispatch_report(self._rcb_ref, self._client_report)
            except Exception as e:
                log.error(f"RCBHandler.trigger 异常: {self._rcb_ref}, {e}")
else:

    class _PyRCBHandler:  # 占位, 不会被使用
        def __init__(self, rcb_ref: str):
            self._rcb_ref = rcb_ref


def _parse_client_report(report, rcb_ref: str) -> ReportDataEntry | None:
    """解析 ClientReport 为 ReportDataEntry

    提取报告中的 rptId、dataSet、confRev、entryId、seqNum、
    timeOfEntry、dataValues、reasonCodes 等信息。

    Args:
        report: libIEC61850 ClientReport 对象
        rcb_ref: RCB 引用路径

    Returns:
        ReportDataEntry 或 None (解析失败)
    """
    try:
        entry = ReportDataEntry()

        # rptId
        try:
            rpt_id = iec61850.ClientReport_getRptId(report)
            if rpt_id:
                entry.rpt_id = str(rpt_id)
        except Exception:
            pass

        # dataSet
        try:
            ds = iec61850.ClientReport_getDataSet(report)
            if ds:
                entry.data_set = str(ds)
        except Exception:
            pass

        # confRev
        with contextlib.suppress(Exception):
            entry.conf_rev = int(iec61850.ClientReport_getConfRev(report))

        # entryId (BRCB)
        try:
            eid = iec61850.ClientReport_getEntryID(report)
            if eid:
                entry.entry_id = bytes(eid)
        except Exception:
            pass

        # seqNum
        with contextlib.suppress(Exception):
            entry.seq_num = int(iec61850.ClientReport_getSeqNum(report))

        # timeOfEntry
        try:
            time_ms = iec61850.ClientReport_getTimeOfEntry(report)
            if time_ms and int(time_ms) > 0:
                entry.time_stamp = datetime.datetime.fromtimestamp(int(time_ms) / 1000.0).strftime(
                    "%Y-%m-%d %H:%M:%S.%f"
                )[:-3]
        except Exception:
            pass

        # receivedAt
        entry.received_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # dataValues (MmsValue 数组) 和 reasonCodes
        try:
            values = iec61850.ClientReport_getValues(report)
            reason_codes = iec61850.ClientReport_getReasonCodes(report)

            if values:
                array_size = 0
                with contextlib.suppress(Exception):
                    array_size = iec61850.MmsValue_getArraySize(values)

                if array_size > 0:
                    for i in range(array_size):
                        try:
                            element = iec61850.MmsValue_getElement(values, i)
                        except Exception:
                            element = None

                        # 尝试获取 reason code
                        reason_str = "unknown"
                        if reason_codes:
                            try:
                                rc = iec61850.ReasonCode_get(reason_codes, i)
                                rc_map = {
                                    0: "data-change",
                                    1: "quality-change",
                                    2: "data-update",
                                    3: "integrity",
                                    4: "gi",
                                }
                                reason_str = rc_map.get(int(rc), f"code={rc}")
                            except Exception:
                                pass

                        if element is not None:
                            val = mms_value_to_python(element)
                            ref_key = f"index[{i}]"

                            # 尝试从 dataSet 成员引用获取 FCDA 路径
                            # (如果 dataSet 信息可用)
                            ref_key = f"data[{i}]"

                            entry.data_values[ref_key] = val
                            entry.reason_codes[ref_key] = reason_str
        except Exception:
            pass

        return entry
    except Exception as e:
        log.error(f"解析 ClientReport 失败: {rcb_ref}, {e}")
        return None
