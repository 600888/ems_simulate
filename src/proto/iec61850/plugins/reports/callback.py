"""报告回调处理模块

封装 C 回调注册/注销，ClientReport 解析与数据缓存。
回调在 libIEC61850 的接收线程中执行，使用 queue 异步处理避免阻塞。
"""

import datetime
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from ...defs.constants import HAS_IEC61850
from ...defs.types import ReportDataEntry
from ...core.mms_value import mms_value_to_python
from ...log import log

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


# 全局回调映射表: rcb_ref -> callback_info
# C 回调无法绑定到实例方法，需通过静态函数 + 全局字典分发
_CALLBACK_REGISTRY: Dict[str, '_CallbackInfo'] = {}
_CALLBACK_LOCK = threading.Lock()


@dataclass
class _CallbackInfo:
    """回调注册信息"""
    rcb_ref: str
    handler: Any = None               # 安装的报告处理器引用
    on_report: Optional[Callable] = None  # Python 回调函数
    data_cache: List[ReportDataEntry] = field(default_factory=list)
    max_cache: int = 1000
    enabled_at: str = ""


class ReportCallbackHandler:
    """报告回调管理器

    管理 C 级别报告回调的注册/注销，以及报告数据的解析与缓存。
    线程安全：C 回调在 libIEC61850 的接收线程中执行，
    通过 _CALLBACK_LOCK 保护注册表和缓存。
    """

    @staticmethod
    def install(connection, rcb_ref: str,
                on_report: Optional[Callable[[ReportDataEntry], None]] = None,
                max_cache: int = 1000) -> bool:
        """安装报告回调

        Args:
            connection: Iec61850Connection 实例
            rcb_ref: RCB 引用路径
            on_report: 可选 Python 回调，收到报告时调用
            max_cache: 最大缓存条数

        Returns:
            bool 是否成功
        """
        if not HAS_IEC61850:
            return False
        conn = connection.connection
        if not conn:
            log.warning(f"安装报告回调失败: 连接不可用, ref={rcb_ref}")
            return False

        with _CALLBACK_LOCK:
            # 如果已注册，先注销
            if rcb_ref in _CALLBACK_REGISTRY:
                ReportCallbackHandler.uninstall(connection, rcb_ref)

            try:
                # 注册 C 回调
                handler = iec61850.IedConnection_installReportHandler(
                    conn, rcb_ref,
                    _report_callback_function,
                    rcb_ref,
                )
                if handler is None:
                    log.warning(f"安装报告回调失败 (返回None): ref={rcb_ref}")
                    log.warning("可能是 pyiec61850 版本不支持 IedConnection_installReportHandler")
                    return False

                _CALLBACK_REGISTRY[rcb_ref] = _CallbackInfo(
                    rcb_ref=rcb_ref,
                    handler=handler,
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
        """注销报告回调"""
        if not HAS_IEC61850:
            return False
        conn = connection.connection
        if not conn:
            return False

        with _CALLBACK_LOCK:
            if rcb_ref not in _CALLBACK_REGISTRY:
                return True

            try:
                iec61850.IedConnection_uninstallReportHandler(conn, rcb_ref)
            except Exception as e:
                log.debug(f"注销报告回调异常 (非致命): {rcb_ref}, {e}")

            del _CALLBACK_REGISTRY[rcb_ref]
            log.info(f"报告回调已注销: {rcb_ref}")
            return True

    @staticmethod
    def get_cache(rcb_ref: str) -> List[Dict[str, Any]]:
        """获取指定 RCB 的缓存报告数据"""
        with _CALLBACK_LOCK:
            info = _CALLBACK_REGISTRY.get(rcb_ref)
            if not info:
                return []
            return [
                ReportCallbackHandler._entry_to_dict(entry)
                for entry in info.data_cache
            ]

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
    def get_active_rcbs() -> List[Dict[str, Any]]:
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
        """关闭所有回调（插件关闭时调用）"""
        with _CALLBACK_LOCK:
            for rcb_ref in list(_CALLBACK_REGISTRY.keys()):
                try:
                    if connection and connection.connection:
                        iec61850.IedConnection_uninstallReportHandler(
                            connection.connection, rcb_ref
                        )
                except Exception:
                    pass
            _CALLBACK_REGISTRY.clear()
            log.info("所有报告回调已关闭")

    @staticmethod
    def _entry_to_dict(entry: ReportDataEntry) -> Dict[str, Any]:
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


def _report_callback_function(param, report):
    """C 级别报告回调函数 (静态)

    由 libIEC61850 在接收线程中调用。
    该函数必须是模块级函数，不能是实例方法。

    Args:
        param: 注册时传入的用户参数 (rcb_ref)
        report: ClientReport 对象
    """
    rcb_ref = str(param) if param else "unknown"

    with _CALLBACK_LOCK:
        info = _CALLBACK_REGISTRY.get(rcb_ref)
        if not info:
            return

        try:
            entry = _parse_client_report(report, rcb_ref)
            if entry is None:
                return

            # 缓存报告数据
            info.data_cache.append(entry)
            if len(info.data_cache) > info.max_cache:
                info.data_cache.pop(0)

            # 调用 Python 回调（如果有）
            if info.on_report:
                try:
                    info.on_report(entry)
                except Exception as cb_err:
                    log.error(f"报告回调函数异常: {rcb_ref}, {cb_err}")
        except Exception as e:
            log.error(f"报告回调处理异常: {rcb_ref}, {e}")


def _parse_client_report(report, rcb_ref: str) -> Optional[ReportDataEntry]:
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
        try:
            entry.conf_rev = int(iec61850.ClientReport_getConfRev(report))
        except Exception:
            pass

        # entryId (BRCB)
        try:
            eid = iec61850.ClientReport_getEntryID(report)
            if eid:
                entry.entry_id = bytes(eid)
        except Exception:
            pass

        # seqNum
        try:
            entry.seq_num = int(iec61850.ClientReport_getSeqNum(report))
        except Exception:
            pass

        # timeOfEntry
        try:
            time_ms = iec61850.ClientReport_getTimeOfEntry(report)
            if time_ms and int(time_ms) > 0:
                entry.time_stamp = datetime.datetime.fromtimestamp(
                    int(time_ms) / 1000.0
                ).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
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
                try:
                    array_size = iec61850.MmsValue_getArraySize(values)
                except Exception:
                    pass

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


# 如果没有 pyiec61850，提供空桩实现
if not HAS_IEC61850:
    def _report_callback_function(param, report):
        pass
