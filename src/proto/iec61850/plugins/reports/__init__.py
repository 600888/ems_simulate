"""Reports 插件 - 报告控制块 (BRCB/URCB) 操作

管理 BRCB/URCB 报告控制块的发现、使能/禁用、GI 触发、
回调注册和报告数据缓存等完整生命周期。
"""

from collections.abc import Callable
import datetime
import re
import threading
import time
from typing import Any, Optional

from src.proto.iec61850.core import Iec61850Connection

from ...core.linked_list import get_list_from_linked_list
from ...core.native_calls import call_gil_safe
from ...defs.constants import HAS_IEC61850, AcsiClass
from ...defs.types import OptFields, RCBInfo, ReportDataEntry, TrgOps
from ...log import log
from ..base import Iec61850Plugin

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850

import contextlib

from .brcb import BrcbHandler
from .callback import ReportCallbackHandler, _report_ref_with_fc
from .urcb import UrcbHandler


class ReportsPlugin:
    """Reports 插件

    管理 BRCB/URCB 报告控制块操作，包括：
    - 发现 RCB (discover_rcbs)
    - 使能/禁用报告 (enable_report / disable_report)
    - 触发通用查询 (trigger_gi)
    - 获取报告数据 (get_report_data)
    - 获取活跃报告列表 (list_active_reports)
    """

    def __init__(self):
        self._connection = None
        self._browse_connection = None
        self._registry = None
        self._client = None
        self._initialized = False
        self._rcb_detail_cache: dict[str, dict[str, Any]] = {}
        self._rcb_type_map: dict[str, str] = {}  # ref -> "BRCB"/"URCB", 发现时填充
        self._operation_lock = threading.RLock()
        self._my_rpt_ids: dict[str, str] = {}  # ref -> 本客户端设置的 rpt_id
        self._primed_rcb_directories: dict[int, set[tuple[str, str]]] = {}

    @property
    def name(self) -> str:
        return "reports"

    @property
    def available(self) -> bool:
        return HAS_IEC61850

    def initialize(self, connection: Any, **kwargs) -> None:
        """初始化插件

        Args:
            connection: Iec61850Connection 实例
            **kwargs: 支持 registry 参数
        """
        self._browse_connection = connection
        self._connection = kwargs.get("report_connection") or connection
        self._registry = kwargs.get("registry")
        self._client = kwargs.get("client")
        self._initialized = True
        log.info("Reports 插件已初始化")

    def shutdown(self) -> None:
        """关闭插件，注销所有活跃报告回调"""
        if self._initialized:
            self.prepare_disconnect()
        self._connection = None
        self._browse_connection = None
        self._registry = None
        self._client = None
        self._rcb_detail_cache.clear()
        self._my_rpt_ids.clear()
        self._primed_rcb_directories.clear()
        self._initialized = False
        log.info("Reports 插件已关闭")

    def _ensure_connection(self) -> bool:
        """按需恢复独立报告 association。"""
        if self._connection and self._connection.is_connected:
            return True
        ensure = getattr(self._client, "_ensure_report_connection", None) if self._client else None
        return bool(callable(ensure) and ensure())

    def prepare_disconnect(self) -> None:
        """先停止报告上送并排空回调，再允许销毁底层连接。"""
        with self._operation_lock:
            if not self._connection:
                return

            active = ReportCallbackHandler.get_active_rcbs(self._connection)
            if self._connection.is_connected:
                for item in active:
                    rcb_ref = str(item.get("rcb_ref") or "")
                    if not rcb_ref:
                        continue
                    with contextlib.suppress(Exception):
                        self._set_rpt_ena_raw(rcb_ref, False)
                # 让接收线程处理禁用响应之前已经到达的最后一批报告；sleep
                # 会释放 GIL，等待中的 SWIG director 因而可以进入并退出。
                if active:
                    time.sleep(0.1)

            ReportCallbackHandler.wait_for_idle(self._connection, timeout=3.0)
            ReportCallbackHandler.shutdown_all(self._connection)
            self._rcb_detail_cache.clear()

    # ==================== RCB 发现 ====================

    def discover_rcbs(self, ld: str = "", ln: str = "") -> list[dict[str, Any]]:
        """发现报告控制块 (BRCB 和 URCB)

        通过 IedConnection_getLogicalNodeDirectory(acsi_class) 发现 BRCB 和 URCB

        Args:
            ld: 逻辑设备名过滤 (空字符串表示全部)
            ln: 逻辑节点名过滤 (空字符串表示全部)

        Returns:
            RCB 信息字典列表
        """
        if not self._ensure_connection():
            log.warning("discover_rcbs: 连接不可用")
            return []

        browse_connection = self._browse_connection or self._connection
        conn = browse_connection.connection if browse_connection else None
        if not conn:
            return []

        # 1. 获取逻辑设备列表
        if ld:
            ld_list = [ld]
            log.debug(f"discover_rcbs: 按指定 LD 过滤: {ld}")
        else:
            try:
                ld_list = browse_connection.browse_logical_devices()
                log.debug(f"discover_rcbs: 发现 {len(ld_list)} 个逻辑设备: {ld_list}")
            except Exception as e:
                log.error(f"discover_rcbs 获取 LD 列表失败: {e}")
                return []

        if not ld_list:
            log.info("discover_rcbs: 未发现任何逻辑设备, 无 RCB 可查找")
            return []

        all_rcbs = []

        for ld_name in ld_list:
            # 2. 获取 LN 列表
            if ln:
                ln_list = [ln]
            else:
                try:
                    ln_list = self._browse_logical_nodes(ld_name)
                except Exception:
                    ln_list = []

            if not ln_list:
                log.debug(f"discover_rcbs: LD={ld_name} 下未发现逻辑节点")
                continue

            # log.debug(f"discover_rcbs: LD={ld_name}, 发现 {len(ln_list)} 个逻辑节点: {ln_list}")

            for ln_name in ln_list:
                ln_ref = f"{ld_name}/{ln_name}"

                # 3. 通过 ACSI 目录发现 BRCB 和 URCB
                rcbs_found = self._discover_rcbs_via_directory(conn, ln_ref, ld_name, ln_name)

                all_rcbs.extend(rcbs_found)

        # 记录每个 RCB 的真实类型 (URCB/BRCB)，供 enable/disable 正确路由
        for r in all_rcbs:
            ref = r.get("ref")
            rtype = r.get("rcb_type")
            if ref and rtype:
                self._rcb_type_map[ref] = rtype

        log.info(f"RCB 发现完成, 共发现 {len(all_rcbs)} 个报告控制块")
        return all_rcbs

    def restore_cached_rcbs(self, rcbs: list[dict[str, Any]]) -> bool:
        """恢复缓存 RCB 元数据，并在状态读取 association 上预热目录。

        RptEnabled 展开的 URCB 实例可能是 association 级对象。只恢复旧
        引用而不查询当前连接的 RCB 目录时，后续 getRCBValues 会返回
        OBJECT_DOES_NOT_EXIST (error=22)。这里只读取涉及的 LN/RCB 目录，
        不重新发现整棵数据模型。
        """
        directory_groups: dict[tuple[str, str], set[str]] = {}
        for item in rcbs:
            ref = str(item.get("ref") or "")
            rcb_type = str(item.get("rcb_type") or self._infer_rcb_type(ref)).upper()
            if ref:
                self._rcb_type_map[ref] = rcb_type
                self._rcb_detail_cache[ref] = dict(item)
            if "/" not in ref or "." not in ref:
                continue
            ln_ref = ref.replace("$", ".").rsplit(".", 1)[0]
            if ln_ref.endswith((".RP", ".BR")):
                ln_ref = ln_ref.rsplit(".", 1)[0]
            directory_groups.setdefault((ln_ref, rcb_type), set()).add(ref.rsplit(".", 1)[-1])

        if not directory_groups:
            return True
        if not self._ensure_connection():
            log.warning("缓存 RCB 目录预热失败: 独立报告连接不可用")
            return False

        # RCB 列表状态由主浏览连接读取。独立报告连接只负责实际使能和
        # 回调，不能拿它遍历整棵模型；部分 IED 会对此返回 error=12
        # (object-reference-invalid)，但这不代表缓存或主连接无效。
        owner = (
            self._browse_connection
            if self._browse_connection and self._browse_connection.is_connected
            else self._connection
        )
        conn = owner.connection if owner and owner.is_connected else None
        if conn is None:
            return False
        association = "browse" if owner is self._browse_connection else "report"

        primed = 0
        for (ln_ref, rcb_type), expected_names in sorted(directory_groups.items()):
            group_key = (ln_ref, rcb_type)
            primed_groups = self._primed_rcb_directories.setdefault(id(conn), set())
            if group_key in primed_groups:
                primed += 1
                continue
            acsi_class = AcsiClass.BRCB if rcb_type == "BRCB" else AcsiClass.URCB
            try:
                result = call_gil_safe(
                    iec61850,
                    "IedConnection_getLogicalNodeDirectory",
                    conn,
                    ln_ref,
                    acsi_class,
                )
                raw = result[0] if isinstance(result, (list, tuple)) else result
                error = result[1] if isinstance(result, (list, tuple)) and len(result) > 1 else 0
                if error != iec61850.IED_ERROR_OK or raw is None:
                    error_text = str(error)
                    with contextlib.suppress(Exception):
                        error_text = f"{error}({iec61850.IedClientError_toString(error)})"
                    log.warning(
                        f"缓存 RCB 目录预热失败: association={association}, "
                        f"ln={ln_ref}, type={rcb_type}, error={error_text}"
                    )
                    continue
                names = get_list_from_linked_list(raw)
                if not names:
                    log.warning(
                        f"缓存 RCB 与当前 IED 不匹配: association={association}, "
                        f"ln={ln_ref}, type={rcb_type}, 在线目录为空"
                    )
                    continue
                if not expected_names.intersection(names):
                    log.warning(
                        f"缓存 RCB 与当前 IED 不匹配: association={association}, "
                        f"ln={ln_ref}, type={rcb_type}, cached={sorted(expected_names)}, online={names}"
                    )
                    continue
                primed += 1
                primed_groups.add(group_key)
                log.debug(
                    f"缓存 RCB 目录已预热: association={association}, ln={ln_ref}, type={rcb_type}, count={len(names)}"
                )
            except Exception as e:
                log.warning(
                    f"缓存 RCB 目录预热异常: association={association}, ln={ln_ref}, type={rcb_type}, error={e}"
                )

        return primed == len(directory_groups)

    def _discover_rcbs_via_directory(self, conn, ln_ref: str, ld_name: str, ln_name: str) -> list[dict]:
        """通过 ACSI 目录发现 RCB

        对所有 LN 执行 ACSI 目录查询，不限于 LLN0。
        IEC 61850 标准允许 RCB 定义在任何逻辑节点下，
        ICD 文件常将 ReportControl 放在功能 LN（如 MMXU、GGIO）下。
        """

        rcbs = []
        for _rcb_type, acsi_class in [("URCB", AcsiClass.URCB), ("BRCB", AcsiClass.BRCB)]:
            try:
                result = iec61850.IedConnection_getLogicalNodeDirectory(conn, ln_ref, acsi_class)

                rcb_names_raw = result[0] if isinstance(result, (list, tuple)) else result

                if rcb_names_raw is None:
                    continue

                rcb_name_list = self._extract_names_from_raw_result(rcb_names_raw, _rcb_type, ln_ref)

                if not rcb_name_list:
                    continue

                # log.debug(f"ACSI目录法: {ln_ref} 下发现 {len(rcb_name_list)} 个 {_rcb_type}")

                for rcb_name in rcb_name_list:
                    rcb_ref = f"{ln_ref}.{rcb_name}"
                    rcb_info = self._get_rcb_info(rcb_ref, _rcb_type, ld_name, ln_name)
                    rcbs.append(rcb_info)
                    # log.debug(f"发现 {_rcb_type}: {rcb_ref}")

            except Exception as e:
                log.error(f"ACSI目录法 发现 {_rcb_type} 异常: {ln_ref}, {e}")
                continue
        return rcbs

    def _extract_names_from_raw_result(self, raw_result, rcb_type: str, ln_ref: str) -> list[str]:
        """从 ACSI 目录原始结果中提取合法的 RCB 名称列表

        过滤规则:
        - 去除 C 指针地址（0x...）
        - 去除 Python repr 垃圾（'sLinkedList', 'at', '*', '\\>' 等）
        - 只保留字母数字和下划线开头的合法名
        """
        raw_names = []
        with contextlib.suppress(Exception):
            raw_names = get_list_from_linked_list(raw_result)

        valid_names = []
        seen = set()
        for name in raw_names:
            if not name or not isinstance(name, str):
                continue
            name = name.strip()
            if not name:
                continue
            # 过滤 C 指针地址
            if name.startswith("0x") or name.startswith("0X"):
                continue
            if re.match(r"^0x[0-9a-fA-F]+", name):
                continue
            # 过滤明显不是 RCB 名的垃圾
            # RCB 名应该是字母开头、长度适中
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
                continue
            if len(name) > 100 or len(name) < 2:
                continue
            # 去重
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            valid_names.append(name)

        if raw_names and not valid_names:
            log.debug(f"ACSI目录法 {rcb_type} {ln_ref}: 原始 {len(raw_names)} 个全部过滤")
        return valid_names

    def _get_rcb_info(self, rcb_ref: str, rcb_type: str, ld_name: str, ln_name: str) -> dict[str, Any]:
        """获取单个 RCB 的详细信息

        尝试通过 getRCBValues 读取属性，失败时返回基本信息。
        """
        # 先构建基本结构
        rcb_name = rcb_ref.split(".")[-1] if "." in rcb_ref else rcb_ref
        info = RCBInfo(
            name=rcb_name,
            ref=rcb_ref,
            rcb_type=rcb_type,
            ld=ld_name,
            ln=ln_name,
        )

        # 尝试读取详细属性
        try:
            if rcb_type == "BRCB":
                detail = BrcbHandler.get_rcb_values(self._connection, rcb_ref)
            else:
                detail = UrcbHandler.get_rcb_values(self._connection, rcb_ref)

            if detail:
                # 合并详细属性
                for field_name in (
                    "rpt_id",
                    "rpt_ena",
                    "data_set_ref",
                    "conf_rev",
                    "buf_time",
                    "intg_period",
                    "sq_num",
                    "trg_ops",
                    "opt_fields",
                ):
                    val = getattr(detail, field_name, None)
                    if val is not None and val != "" and val is not False:
                        if isinstance(val, (TrgOps, OptFields)):
                            setattr(info, field_name, val)
                        else:
                            setattr(info, field_name, val)

                if rcb_type == "BRCB":
                    if detail.entry_id:
                        info.entry_id = detail.entry_id
                    if detail.time_of_entry:
                        info.time_of_entry = detail.time_of_entry
                    if detail.purge_buf:
                        info.purge_buf = detail.purge_buf
                    if detail.owner:
                        info.owner = detail.owner
                    info.resv_tms = detail.resv_tms
                elif rcb_type == "URCB":
                    if detail.owner:
                        info.owner = detail.owner
                    if detail.resv:
                        info.resv = detail.resv
        except Exception as e:
            log.debug(f"读取 RCB 属性失败: {rcb_ref}, {e}")

        result = self._rcb_info_to_dict(info)
        self._rcb_detail_cache[rcb_ref] = result
        return result

    def _rcb_info_to_dict(self, info: RCBInfo) -> dict[str, Any]:
        """将 RCBInfo 对象转为字典"""
        result = {
            "name": info.name,
            "ref": info.ref,
            "rcb_type": info.rcb_type,
            "ld": info.ld,
            "ln": info.ln,
            "rpt_id": info.rpt_id,
            "rpt_ena": info.rpt_ena,
            "data_set_ref": info.data_set_ref,
            "conf_rev": info.conf_rev,
            "buf_time": info.buf_time,
            "intg_period": info.intg_period,
            "sq_num": info.sq_num,
            "purge_buf": info.purge_buf,
            "entry_id": info.entry_id.hex() if info.entry_id else None,
            "time_of_entry": info.time_of_entry,
            "owner": info.owner,
            "resv": info.resv,
            "resv_tms": info.resv_tms,
            "trg_ops": {
                "dchg": info.trg_ops.dchg,
                "qchg": info.trg_ops.qchg,
                "dupd": info.trg_ops.dupd,
                "period": info.trg_ops.period,
                "gi": info.trg_ops.gi,
            },
            "opt_fields": {
                "seq_num": info.opt_fields.seq_num,
                "time_stamp": info.opt_fields.time_stamp,
                "data_set": info.opt_fields.data_set,
                "reason_code": info.opt_fields.reason_code,
                "data_ref": info.opt_fields.data_ref,
                "entry_id": info.opt_fields.entry_id,
                "config_ref": info.opt_fields.config_ref,
                "buf_ovfl": info.opt_fields.buf_ovfl,
            },
            "active": ReportCallbackHandler.is_active(info.ref, self._connection),
        }
        result["reserved"] = bool(info.resv or info.resv_tms != 0)
        # 兼容未实现 Owner/ResvTms 的旧版 IED：非本客户端订阅且 RptEna
        # 已置位时，该实例同样无法使用，应显示为被其他客户端锁定。
        # 用 rpt_id 区分：若 rpt_id 匹配本客户端写入的值，说明是自己使能后的
        # 残留状态，不应视为其他客户端加锁。
        my_rpt_id = self._my_rpt_ids.get(info.ref)
        locked_by_other = result["reserved"] or (info.rpt_ena and info.rpt_id != my_rpt_id)
        result["locked"] = bool(not result["active"] and locked_by_other)
        return result

    def refresh_rcb_states(self, rcbs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """刷新已发现 RCB 的实时使能和预留状态。

        RCB 的目录与配置继续使用缓存；易变化的 RptEna/Resv/ResvTms/Owner
        每次请求列表时从 IED 读取。状态读取使用主浏览连接，避免与报告回调连接竞争。
        """
        connection = self._browse_connection or self._connection
        if not connection or not connection.is_connected:
            return list(rcbs)

        # 缓存可能早于主连接加载。首次状态刷新时惰性预热当前 association；
        # 若缓存与在线 IED 不匹配，避免对数百个无效引用逐个读取并刷屏。
        if rcbs and not self.restore_cached_rcbs(rcbs):
            log.warning("RCB 状态刷新已跳过: 缓存目录尚未在当前连接上恢复或与在线 IED 不匹配")
            return list(rcbs)

        refreshed: list[dict[str, Any]] = []
        success_count = 0
        fail_count = 0
        for cached in rcbs:
            item = dict(cached)
            rcb_ref = str(item.get("ref") or "")
            rcb_type = str(item.get("rcb_type") or self._infer_rcb_type(rcb_ref))
            try:
                operation = (
                    connection.native_operation()
                    if hasattr(connection, "native_operation")
                    else contextlib.nullcontext()
                )
                with operation:
                    if rcb_type == "URCB":
                        detail = UrcbHandler.get_rcb_values(connection, rcb_ref)
                    else:
                        detail = BrcbHandler.get_rcb_values(connection, rcb_ref)
                if detail is not None:
                    success_count += 1
                    active = ReportCallbackHandler.is_active(rcb_ref, self._connection)
                    reserved = bool(detail.resv or detail.resv_tms != 0)
                    my_rpt_id = self._my_rpt_ids.get(rcb_ref)
                    locked_by_other = reserved or (detail.rpt_ena and detail.rpt_id != my_rpt_id)
                    item.update(
                        rpt_ena=detail.rpt_ena,
                        owner=detail.owner,
                        resv=detail.resv,
                        resv_tms=detail.resv_tms,
                        rpt_id=detail.rpt_id,
                        reserved=reserved,
                        active=active,
                        locked=bool(not active and locked_by_other),
                        data_set_ref=detail.data_set_ref or item.get("data_set_ref", ""),
                        intg_period=detail.intg_period or item.get("intg_period", 0),
                    )
                    self._rcb_detail_cache[rcb_ref] = item
                else:
                    fail_count += 1
            except Exception as e:
                fail_count += 1
                log.debug(f"刷新 RCB 占用状态失败: ref={rcb_ref}, {e}")
            refreshed.append(item)
        total = len(rcbs)
        if fail_count > 0 and fail_count >= total // 2:
            log.warning(
                f"刷新 RCB 状态: {success_count}/{total} 成功, {fail_count}/{total} 失败 "
                f"(远程 IED 可能未配置这些报告控制块)"
            )
        elif fail_count > 0:
            log.info(f"刷新 RCB 状态: {success_count}/{total} 成功, {fail_count}/{total} 失败")
        return refreshed

    # ==================== 报告配置应用 ====================

    def apply_config(
        self,
        rcb_ref: str,
        rpt_ena: bool,
        trg_ops: dict[str, bool] | None = None,
        opt_fields: dict[str, bool] | None = None,
        on_report: Callable[[ReportDataEntry], None] | None = None,
    ) -> bool:
        """应用报告配置

        报告使能时跳过 TrgOps/OptFields 写入 (使能状态下无法修改属性)。
        用户需先禁用报告，修改配置，再使能。

        根据参数决定行为:
        - rpt_ena 变化: 仅设置 RptEna 开关 (使能/禁用)
        - rpt_ena 不变且当前禁用: 仅写入 TrgOps/OptFields
        - rpt_ena 不变且当前使能: 跳过 (使能时无法修改属性)

        如果底层 MMS 会话已经半失效，第一次 RCB 读写可能返回 error=3。
        这种情况下清理旧报告回调并重建连接后重试一次，等价于用户手动重启客户端。
        """
        with self._operation_lock:
            if not self._ensure_connection():
                log.warning(f"应用报告配置失败: 独立报告连接不可用, ref={rcb_ref}")
                return False
            if self._apply_config_once(rcb_ref, rpt_ena, trg_ops, opt_fields, on_report):
                return True

            if not self._recover_connection_for_report_operation(rcb_ref):
                return False

            return self._apply_config_once(rcb_ref, rpt_ena, trg_ops, opt_fields, on_report)

    def apply_config_batch(
        self,
        rcb_refs: list[str],
        rpt_ena: bool,
        trg_ops: dict[str, bool] | None = None,
        opt_fields: dict[str, bool] | None = None,
    ) -> list[tuple[str, bool, str]]:
        """在同一操作锁内完成一个批次，防止并发批次逐项交叉。"""
        results: list[tuple[str, bool, str]] = []
        with self._operation_lock:
            if not self._ensure_connection():
                return [(rcb_ref, False, "独立报告连接不可用") for rcb_ref in rcb_refs]
            for rcb_ref in rcb_refs:
                try:
                    # 批次中不做会清空其他已成功订阅的全连接重建；单项失败
                    # 只影响本项，下一项仍可继续。
                    ok = self._apply_config_once(rcb_ref, rpt_ena, trg_ops, opt_fields)
                    results.append((rcb_ref, ok, "" if ok else "操作失败"))
                except Exception as exc:
                    log.error(f"批量应用报告配置异常: ref={rcb_ref}, {exc}", exc_info=True)
                    results.append((rcb_ref, False, str(exc)))
        return results

    def _apply_config_once(
        self,
        rcb_ref: str,
        rpt_ena: bool,
        trg_ops: dict[str, bool] | None = None,
        opt_fields: dict[str, bool] | None = None,
        on_report: Callable[[ReportDataEntry], None] | None = None,
    ) -> bool:
        if not self._connection or not self._connection.is_connected:
            log.warning(f"应用报告配置失败: 连接不可用, ref={rcb_ref}")
            return False

        current_rpt_ena = False
        detail = self.get_rcb_detail(rcb_ref)
        if detail:
            current_rpt_ena = bool(detail.get("rpt_ena", False))

        if rpt_ena != current_rpt_ena:
            if rpt_ena:
                # 使能前先写入 TrgOps/OptFields（RptEna=False 时才能修改这些属性）
                if trg_ops is not None or opt_fields is not None:
                    config_ok = self._set_config(rcb_ref, trg_ops, opt_fields)
                    if not config_ok:
                        log.warning(f"使能前设置 TrgOps/OptFields 失败, 继续尝试使能: {rcb_ref}")
                return self._enable_report(rcb_ref, on_report=on_report)
            return self._disable_report(rcb_ref)

        if current_rpt_ena:
            log.info(f"报告已使能，跳过配置写入: {rcb_ref}")
            return True

        if trg_ops is not None or opt_fields is not None:
            return self._set_config(rcb_ref, trg_ops, opt_fields)

        return True

    def _recover_connection_for_report_operation(self, rcb_ref: str) -> bool:
        """报告 RCB 操作失败后重建 MMS 连接并清理旧回调。"""
        if not self._connection:
            return False

        log.warning(f"报告配置失败，尝试重建 IEC61850 客户端连接后重试: {rcb_ref}")
        try:
            self.prepare_disconnect()
        except Exception as e:
            log.debug(f"报告重连前清理回调失败 (非致命): {rcb_ref}, {e}")

        try:
            reconnect = getattr(self._connection, "try_reconnect", None)
            if callable(reconnect):
                ok = reconnect(max_retries=1, interval=0.2)
            else:
                with contextlib.suppress(Exception):
                    self._connection.disconnect()
                ok = self._connection.connect(auto_discover=False)
        except Exception as e:
            log.warning(f"报告配置重连异常: {rcb_ref}, {e}")
            return False

        if ok:
            self._rcb_detail_cache.clear()
            log.info(f"报告配置重连成功，准备重试: {rcb_ref}")
            return True

        log.warning(f"报告配置重连失败: {rcb_ref}")
        return False

    def _set_config(
        self,
        rcb_ref: str,
        trg_ops: dict[str, bool] | None = None,
        opt_fields: dict[str, bool] | None = None,
    ) -> bool:
        """设置报告触发选项和可选字段 (内部方法，需在 RptEna=False 时调用)"""
        # 构建 TrgOps
        trg = TrgOps()
        if trg_ops:
            trg.dchg = trg_ops.get("dchg", True)
            trg.qchg = trg_ops.get("qchg", False)
            trg.dupd = trg_ops.get("dupd", False)
            trg.period = trg_ops.get("period", False)
            trg.gi = trg_ops.get("gi", False)

        # 构建 OptFields
        opt = OptFields()
        if opt_fields:
            opt.seq_num = opt_fields.get("seq_num", True)
            opt.time_stamp = opt_fields.get("time_stamp", True)
            opt.data_set = opt_fields.get("data_set", True)
            opt.reason_code = opt_fields.get("reason_code", True)
            opt.data_ref = opt_fields.get("data_ref", False)
            opt.entry_id = opt_fields.get("entry_id", True)
            opt.config_ref = opt_fields.get("config_ref", False)
            opt.buf_ovfl = opt_fields.get("buf_ovfl", False)

        # 判断 RCB 类型
        rcb_type = self._infer_rcb_type(rcb_ref)

        # 写入 TrgOps + OptFields (RptEna=False 状态)
        if rcb_type == "BRCB":
            success = BrcbHandler.set_rpt_ena(self._connection, rcb_ref, False, trg, opt)
        else:
            success = UrcbHandler.set_rpt_ena(self._connection, rcb_ref, False, trg, opt)

        if success:
            log.info(f"报告配置已更新: {rcb_ref}")
        else:
            log.warning(f"设置报告配置失败: {rcb_ref}")

        return success

    def _enable_report(
        self,
        rcb_ref: str,
        on_report: Callable[[ReportDataEntry], None] | None = None,
    ) -> bool:
        """Enable a report and install its callback before RptEna=True."""
        rcb_type = self._infer_rcb_type(rcb_ref)

        # 读取 RCB 的 RptId, 用于报告回调匹配。
        # 参考 libiec61850 C 例子 client_example_reporting.c:
        #   IedConnection_installReportHandler(con, "...EventsRCB",
        #       ClientReportControlBlock_getRptId(rcb), ...);
        # RCBSubscriber 需要正确的 RptId 才能将服务器推送的报告路由到
        # 对应的 RCBHandler.trigger 回调。若传空字符串, 报告无法匹配,
        # 回调不会被触发, 导致报告数据缓存为空。
        rpt_id = ""
        data_set_ref = ""

        # 优先通过 getRCBValues 直接读取 RptId（比 get_rcb_detail 更直接可靠）
        try:
            if rcb_type == "BRCB":
                rcb_info = BrcbHandler.get_rcb_values(self._connection, rcb_ref)
            else:
                rcb_info = UrcbHandler.get_rcb_values(self._connection, rcb_ref)
            if rcb_info and hasattr(rcb_info, "rpt_id") and rcb_info.rpt_id:
                rpt_id = str(rcb_info.rpt_id)
                data_set_ref = str(rcb_info.data_set_ref or "")
                log.info(f"_enable_report: 直接读取 RptId 成功: {rcb_ref}, rpt_id={rpt_id!r}")
            elif rcb_info:
                data_set_ref = str(rcb_info.data_set_ref or "")
                log.info(f"_enable_report: 直接读取 RptId 为空: {rcb_ref}, data_set_ref={data_set_ref!r}")
        except Exception as e:
            log.warning(f"_enable_report: 直接读取 RptId 失败: {rcb_ref}, {e}, 尝试从缓存读取")

        # 备用：从缓存中读取
        if not rpt_id:
            try:
                detail = self.get_rcb_detail(rcb_ref)
                if detail:
                    rpt_id = str(detail.get("rpt_id", "") or "")
                    if not data_set_ref:
                        data_set_ref = str(detail.get("data_set_ref", "") or "")
                    log.info(f"_enable_report: 从缓存读取 RptId: {rcb_ref}, rpt_id={rpt_id!r}")
            except Exception as e:
                log.warning(f"_enable_report: 从缓存读取 RptId 失败: {rcb_ref}, {e}")

        # RptEnabled 展开的实例常常仍返回 SCL 中的基础 RptId。使能前将
        # 实例名尾部编号写入远端 RCB，确保设备上送值和本地订阅值一致。
        unique_rpt_id = self._derive_instance_rpt_id(rcb_ref, rpt_id)
        if unique_rpt_id != rpt_id:
            if rcb_type == "BRCB":
                rpt_id_updated = BrcbHandler.set_rpt_id(self._connection, rcb_ref, unique_rpt_id)
            else:
                rpt_id_updated = UrcbHandler.set_rpt_id(self._connection, rcb_ref, unique_rpt_id)

            if not rpt_id_updated:
                log.error(
                    f"_enable_report: 无法为 RCB 写入唯一 RptId: ref={rcb_ref}, old={rpt_id!r}, new={unique_rpt_id!r}"
                )
                return False

            rpt_id = unique_rpt_id
            cached_detail = self._rcb_detail_cache.get(rcb_ref)
            if cached_detail is not None:
                cached_detail["rpt_id"] = rpt_id

        # 记录本客户端设置的 rpt_id，用于 locked 判断时区分是否为其他客户端使能
        self._my_rpt_ids[rcb_ref] = rpt_id

        if not rpt_id:
            log.error(f"_enable_report: RptId 为空且无法生成唯一值: ref={rcb_ref}, rcb_type={rcb_type}")
            return False

        # 查询数据集成员引用列表，用于报告数据解析时将 data[i] 映射为具体引用
        dataset_members: list[str] = []
        if data_set_ref:
            try:
                datasets = getattr(self._client, "datasets", None) if self._client else None
                if datasets:
                    members = datasets.browse_dataset_directory(data_set_ref)
                    if members:
                        dataset_members = []
                        for member in members:
                            member_ref = str(member.get("ref", member.get("fcda_ref", "")) or "")
                            if member_ref:
                                dataset_members.append(_report_ref_with_fc(member_ref, str(member.get("fc", ""))))
                        log.info(
                            f"_enable_report: 获取数据集成员引用成功: ds={data_set_ref}, count={len(dataset_members)}"
                        )
            except Exception as e:
                log.warning(f"_enable_report: 获取数据集成员失败: {data_set_ref}, {e}")

        callback_ok = ReportCallbackHandler.install(
            self._connection,
            rcb_ref,
            on_report=on_report,
            rcb_type=rcb_type,
            rpt_id=rpt_id,
            dataset_members=dataset_members,
        )
        if not callback_ok:
            log.warning(f"install report callback failed: {rcb_ref}")
            self._my_rpt_ids.pop(rcb_ref, None)
            return False

        if rcb_type == "BRCB":
            success = BrcbHandler.set_rpt_ena(self._connection, rcb_ref, True)
        else:
            success = UrcbHandler.set_rpt_ena(self._connection, rcb_ref, True)

        if not success:
            log.warning(f"set RptEna=True failed: {rcb_ref}")
            ReportCallbackHandler.deactivate(self._connection, rcb_ref)
            self._my_rpt_ids.pop(rcb_ref, None)
            return False

        log.info(f"report enabled: {rcb_ref}")
        return True

    @staticmethod
    def _derive_instance_rpt_id(rcb_ref: str, rpt_id: str) -> str:
        """Derive the runtime RptId from an RptEnabled instance name."""
        normalized_ref = (rcb_ref or "").replace("$", ".")
        rcb_name = normalized_ref.rsplit(".", 1)[-1]
        if not rcb_name:
            return rpt_id

        suffix_match = re.search(r"(\d{2})$", rcb_name)
        if not rpt_id:
            return rcb_name
        if not suffix_match:
            return rpt_id

        suffix = suffix_match.group(1)
        return rpt_id if rpt_id.endswith(suffix) else f"{rpt_id}{suffix}"

    def _disable_report(self, rcb_ref: str) -> bool:
        """Disable a report and remove its callback subscription."""
        rcb_type = self._infer_rcb_type(rcb_ref)
        try:
            if rcb_type == "BRCB":
                success = BrcbHandler.disable_direct(self._connection, rcb_ref)
            else:
                success = UrcbHandler.disable_direct(self._connection, rcb_ref)

            if not success:
                log.warning(f"set RptEna=False failed: {rcb_ref}")
                return False
        except Exception as e:
            log.error(f"disable report failed: {rcb_ref}, {e}")
            return False

        # 不在报告接收高峰中销毁 SWIG/C++ subscriber。先暂停 Python
        # 分发并排空已经进入的回调，后续使能复用同一原生订阅；连接关闭时
        # 再由 shutdown_all 统一注销。
        ReportCallbackHandler.deactivate(self._connection, rcb_ref, timeout=3.0)

        self._my_rpt_ids.pop(rcb_ref, None)
        log.info(f"report disabled: {rcb_ref}")
        return True

    def _set_rpt_ena_raw(self, rcb_ref: str, enable: bool) -> bool:
        """仅设置 RptEna，不操作回调"""
        rcb_type = self._infer_rcb_type(rcb_ref)
        if not enable:
            # 禁用走 disable_direct，简单直接
            if rcb_type == "BRCB":
                return BrcbHandler.disable_direct(self._connection, rcb_ref)
            else:
                return UrcbHandler.disable_direct(self._connection, rcb_ref)
        # 使能
        if rcb_type == "BRCB":
            return BrcbHandler.set_rpt_ena(self._connection, rcb_ref, True)
        else:
            return UrcbHandler.set_rpt_ena(self._connection, rcb_ref, True)

    # ==================== GI 触发 ====================

    def trigger_gi(self, rcb_ref: str) -> bool:
        """触发通用查询 (GI)，立即生成一次完整报告"""
        with self._operation_lock:
            if not self._ensure_connection():
                return False

            rcb_type = self._infer_rcb_type(rcb_ref)
            if rcb_type == "BRCB":
                return BrcbHandler.trigger_gi(self._connection, rcb_ref)
            return self._trigger_urcb_software_gi(rcb_ref)

    def _trigger_urcb_software_gi(self, rcb_ref: str) -> bool:
        """通过一次 DataSet 批读生成 URCB 软件 GI，并写入报告缓存。

        软件 GI 必须保持批量语义：NamedVariableList 读取失败时直接返回失败，
        不允许退化为逐成员 ``readObject``，避免大 DataSet 触发大量 MMS 请求。
        """
        ReportCallbackHandler.mark_pending_gi(rcb_ref, connection=self._connection)

        # 强制从 IED 获取最新 data_set_ref，覆盖缓存/SCL 中的差异。
        # 在线发现模式从 ClientReportControlBlock_getDataSetReference 获取
        # 纯 DataSet 名（无 LN$ 前缀），而 SCL 缓存可能拼入 LN 前缀，导致
        # MMS readNamedVariableListValues 找不到对象（MMS error 81）。
        fresh = None
        try:
            fresh = self.get_rcb_detail(rcb_ref)
        except Exception as e:
            log.debug(f"get_rcb_detail exception: {rcb_ref}, {e}")

        if fresh:
            self._rcb_detail_cache[rcb_ref] = fresh
        else:
            fresh = {}

        data_set_ref = str((fresh or self._rcb_detail_cache.get(rcb_ref) or {}).get("data_set_ref") or "")
        log.info(f"URCB GI 调试: rcb_ref={rcb_ref}, fresh_from_ied=bool({bool(fresh)}), data_set_ref={data_set_ref!r}")
        rpt_id = str((fresh or {}).get("rpt_id") or self._rcb_detail_cache.get(rcb_ref, {}).get("rpt_id") or "")
        conf_rev = int((fresh or {}).get("conf_rev") or self._rcb_detail_cache.get(rcb_ref, {}).get("conf_rev") or 1)

        if not data_set_ref:
            log.warning(f"URCB 软件 GI 失败: RCB 未绑定 DataSet, ref={rcb_ref}")
            return False

        datasets = getattr(self._client, "datasets", None) if self._client else None
        if not datasets:
            log.warning(f"URCB 软件 GI 失败: DataSets 插件不可用, ref={rcb_ref}")
            return False

        try:
            values = datasets.read_dataset_values(data_set_ref, allow_member_fallback=False)
        except Exception as e:
            log.warning(f"URCB 软件 GI 读取 DataSet 异常: ref={rcb_ref}, ds={data_set_ref}, {e}")
            return False

        if not values:
            log.warning(f"URCB 软件 GI 读取 DataSet 为空: ref={rcb_ref}, ds={data_set_ref}")
            return False

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        entry = ReportDataEntry(
            seq_num=0,
            time_stamp=now,
            reason_codes={key: "gi" for key in values.keys()},
            data_values=values,
            conf_rev=conf_rev,
            data_set=data_set_ref,
            rpt_id=rpt_id,
            received_at=now,
        )
        ok = ReportCallbackHandler.append_cache_entry(rcb_ref, entry, self._connection)
        if ok:
            log.info(f"URCB 软件 GI 已写入缓存: ref={rcb_ref}, ds={data_set_ref}, values={len(values)}")
        return ok

    # ==================== 报告数据查询 ====================

    def get_report_data(self, rcb_ref: str, limit: int = 100) -> list[dict[str, Any]]:
        """获取指定 RCB 最近接收的报告数据

        Args:
            rcb_ref: RCB 引用路径
            limit: 最多返回条数

        Returns:
            报告数据字典列表
        """
        data = ReportCallbackHandler.get_cache(rcb_ref, self._connection)
        if limit > 0:
            data = data[-limit:]
        return data

    def get_report_data_state(self, rcb_ref: str) -> tuple[int, int]:
        """获取报告缓存数量和最新 uid，不序列化大体积 data_values。"""
        return ReportCallbackHandler.get_cache_state(rcb_ref, self._connection)

    def get_report_summaries(self, rcb_ref: str, limit: int = 100) -> list[dict[str, Any]]:
        """获取报告历史摘要列表，不返回 data_values。"""
        return ReportCallbackHandler.get_cache_summaries(rcb_ref, limit, self._connection)

    def get_report_entry(
        self,
        rcb_ref: str,
        *,
        uid: int | None = None,
        latest: bool = True,
    ) -> dict[str, Any] | None:
        """按需获取一条完整报告。"""
        return ReportCallbackHandler.get_cache_entry(
            rcb_ref,
            uid=uid,
            latest=latest,
            connection=self._connection,
        )

    def clear_report_data(self, rcb_ref: str) -> None:
        """清除指定 RCB 的缓存数据"""
        ReportCallbackHandler.clear_cache(rcb_ref, self._connection)

    # ==================== 状态查询 ====================

    def list_active_reports(self) -> list[dict[str, Any]]:
        """列出当前活跃 (已使能) 的报告订阅

        Returns:
            活跃报告信息列表
        """
        return ReportCallbackHandler.get_active_rcbs(self._connection)

    def is_active(self, rcb_ref: str) -> bool:
        """检查指定 RCB 是否处于活跃状态"""
        return ReportCallbackHandler.is_active(rcb_ref, self._connection)

    def get_rcb_detail(self, rcb_ref: str) -> dict[str, Any] | None:
        """获取单个 RCB 的详细信息

        Args:
            rcb_ref: RCB 引用路径

        Returns:
            RCB 详细信息字典，失败返回 None
        """
        with self._operation_lock:
            if not self._ensure_connection():
                return None

            rcb_type = self._infer_rcb_type(rcb_ref)

            rcb_ref.split(".")[-1] if "." in rcb_ref else rcb_ref
            ld_name = ""
            ln_name = ""
            if rcb_ref and "/" in rcb_ref:
                parts = rcb_ref.split("/", 1)
                ld_name = parts[0]
                ln_part = parts[1].split(".")[0] if "." in parts[1] else parts[1]
                ln_name = ln_part

            return self._get_rcb_info(rcb_ref, rcb_type, ld_name, ln_name)

    # ==================== 内部辅助 ====================

    def _infer_rcb_type(self, rcb_ref: str) -> str:
        """从 RCB 引用推断类型 (BRCB/URCB)

        优先使用发现时记录的真实类型，其次按名称前缀，默认 BRCB。
        """
        if rcb_ref in self._rcb_type_map:
            return self._rcb_type_map[rcb_ref]
        rcb_name = rcb_ref.split(".")[-1].lower() if "." in rcb_ref else rcb_ref.lower()
        if rcb_name.startswith("urcb"):
            return "URCB"
        if rcb_name.startswith("brcb"):
            return "BRCB"
        # 自定义命名启发: rp* 多为非缓冲(URCB), br* 为缓冲(BRCB)
        if rcb_name.startswith("rp"):
            return "URCB"
        if rcb_name.startswith("br"):
            return "BRCB"
        # 默认通过 AcsiClass 发现判断
        return "BRCB"

    def _browse_logical_nodes(self, ld: str) -> list[str]:
        """浏览指定逻辑设备下的逻辑节点

        使用 IedConnection_getLogicalDeviceDirectory 获取 LN 列表，
        正确处理错误码和返回值。
        """
        browse_connection = self._browse_connection or self._connection
        if not browse_connection or not browse_connection.connection:
            return []
        conn = browse_connection.connection
        try:
            result = iec61850.IedConnection_getLogicalDeviceDirectory(conn, ld)
            if isinstance(result, (list, tuple)):
                ln_raw = result[0]
                error = result[1] if len(result) > 1 else 0
            else:
                ln_raw = result
                error = 0

            if error != iec61850.IED_ERROR_OK:
                log.debug(f"获取 LN 目录失败: {ld}, error={error}")
                return []

            if ln_raw:
                ln_list = get_list_from_linked_list(ln_raw)
                # log.debug(f"LD={ld} 下发现 LN: {ln_list}")
                return ln_list
        except Exception as e:
            log.debug(f"浏览 LN 失败: {ld}, {e}")
        return []
