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
    """规范化 RCB 引用为 MMS 引用格式 (LD/LN$FC$rcbName)

    RCBSubscriber.setRcbReference / IedConnection_uninstallReportHandler
    要求使用 MMS 层引用格式, FC 段以 '$' 分隔 (如 LD/LLN0$BR$brcb01),
    而非 IEC 61850 约束引用格式 (LD/LLN0.BR.brcb01)。

    rp*/urcb* -> $RP$ (非缓冲); 其余 -> $BR$ (缓冲)。
    已含 '$' FC 段则原样返回; 已含 '.' FC 段则转换为 '$'。
    """
    if not rcb_ref or "/" not in rcb_ref:
        return rcb_ref

    # 已是 MMS 格式 LD/LN$FC$name
    if "$" in rcb_ref:
        return rcb_ref

    # IEC 61850 约束引用格式 LD/LN.FC.name -> MMS 格式 LD/LN$FC$name
    if "." in rcb_ref:
        ln_part, name = rcb_ref.rsplit(".", 1)
        # 检查是否已含 FC 段 (LD/LN.FC.name)
        parts = ln_part.split(".")
        if len(parts) >= 2 and parts[-1] in ("BR", "RP"):
            # 已含 FC: LD/LN.FC.name -> LD/LN$FC$name
            fc = parts[-1]
            ln_only = ".".join(parts[:-1])
            return f"{ln_only}${fc}${name}"
        # 不含 FC, 按名称前缀推断
        low = name.lower()
        fc = "RP" if (low.startswith("rp") or low.startswith("urcb")) else "BR"
        return f"{ln_part}${fc}${name}"

    # 无 '.' 也无 '$', 仅 LD/LN, 无法推断 FC, 原样返回
    return rcb_ref


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
        nref = _normalize_ref(rcb_ref)

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
                    iec61850.IedConnection_uninstallReportHandler(conn, _normalize_ref(ref))
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
                log.info(f"RCBHandler.trigger: _client_report={cr}, rcb_ref={self._rcb_ref}")
                _dispatch_report(self._rcb_ref, cr)
            except Exception as e:
                log.error(f"RCBHandler.trigger 异常: {self._rcb_ref}, {e}", exc_info=True)
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
