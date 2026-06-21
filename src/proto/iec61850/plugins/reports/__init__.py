"""Reports 插件 - 报告控制块 (BRCB/URCB) 操作

管理 BRCB/URCB 报告控制块的发现、使能/禁用、GI 触发、
回调注册和报告数据缓存等完整生命周期。
"""

from collections.abc import Callable
import re
import time
from typing import Any, Optional

from ...core.linked_list import get_list_from_linked_list
from ...defs.constants import HAS_IEC61850, AcsiClass
from ...defs.types import OptFields, RCBInfo, ReportDataEntry, TrgOps
from ...log import log
from ..base import Iec61850Plugin

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850

import contextlib

from .brcb import BrcbHandler
from .callback import ReportCallbackHandler
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
        self._registry = None
        self._initialized = False
        self._rcb_type_map: dict[str, str] = {}  # ref -> "BRCB"/"URCB", 发现时填充

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
        self._connection = connection
        self._registry = kwargs.get("registry")
        self._initialized = True
        log.info("Reports 插件已初始化")

    def shutdown(self) -> None:
        """关闭插件，注销所有活跃报告回调"""
        if self._initialized:
            ReportCallbackHandler.shutdown_all(self._connection)
        self._connection = None
        self._registry = None
        self._initialized = False
        log.info("Reports 插件已关闭")

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
        if not self._connection or not self._connection.is_connected:
            log.warning("discover_rcbs: 连接不可用")
            return []

        conn = self._connection.connection
        if not conn:
            return []

        # 1. 获取逻辑设备列表
        if ld:
            ld_list = [ld]
            log.debug(f"discover_rcbs: 按指定 LD 过滤: {ld}")
        else:
            try:
                ld_list = self._connection.browse_logical_devices()
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

            log.debug(f"discover_rcbs: LD={ld_name}, 发现 {len(ln_list)} 个逻辑节点: {ln_list}")

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

    def _discover_rcbs_via_directory(self, conn, ln_ref: str, ld_name: str, ln_name: str) -> list[dict]:
        """通过 ACSI 目录发现 RCB

        仅对 LLN0 执行 ACSI 目录查询（RCB 按 IEC 61850 标准只定义在 LLN0 下）。
        非 LLN0 节点直接返回空。
        """
        if ln_name.upper() != "LLN0":
            return []

        rcbs = []
        for _rcb_type, acsi_class in [("URCB", AcsiClass.URCB), ("BRCB", AcsiClass.BRCB)]:
            try:
                result = iec61850.IedConnection_getLogicalNodeDirectory(conn, ln_ref, acsi_class)

                rcb_names_raw = result[0] if isinstance(result, (list, tuple)) else result

                if rcb_names_raw is None:
                    log.debug(f"ACSI目录法: {_rcb_type} {ln_ref} 返回空")
                    continue

                rcb_name_list = self._extract_names_from_raw_result(rcb_names_raw, _rcb_type, ln_ref)

                if not rcb_name_list:
                    log.debug(f"ACSI目录法: {_rcb_type} {ln_ref} 无有效 RCB 名称")
                    continue

                log.info(f"ACSI目录法: {ln_ref} 下发现 {len(rcb_name_list)} 个 {_rcb_type}: {rcb_name_list}")

                for rcb_name in rcb_name_list:
                    rcb_ref = f"{ln_ref}.{rcb_name}"
                    rcb_info = self._get_rcb_info(rcb_ref, _rcb_type, ld_name, ln_name)
                    rcbs.append(rcb_info)
                    log.info(f"发现 {_rcb_type}: {rcb_ref}")

            except Exception as e:
                log.debug(f"ACSI目录法 发现 {_rcb_type} 异常: {ln_ref}, {e}")
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
        elif valid_names:
            log.debug(f"ACSI目录法 {rcb_type} {ln_ref}: 提取 {len(valid_names)}/{len(raw_names)} 个合法名")

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
                    if detail.time_of_entry is not None and detail.time_of_entry > 0:
                        info.time_of_entry = detail.time_of_entry
                    if detail.purge_buf:
                        info.purge_buf = detail.purge_buf
                elif rcb_type == "URCB":
                    if detail.owner:
                        info.owner = detail.owner
                    if detail.resv:
                        info.resv = detail.resv
        except Exception as e:
            log.debug(f"读取 RCB 属性失败: {rcb_ref}, {e}")

        return self._rcb_info_to_dict(info)

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
            "active": ReportCallbackHandler.is_active(info.ref),
        }
        return result

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

        Args:
            rcb_ref: RCB 引用路径
            rpt_ena: 报告使能目标状态
            trg_ops: 触发选项字典
            opt_fields: 可选字段字典
            on_report: 报告接收回调 (可选)

        Returns:
            bool 是否成功
        """
        if not self._connection or not self._connection.is_connected:
            log.warning(f"应用报告配置失败: 连接不可用, ref={rcb_ref}")
            return False

        # 读取当前 RptEna 状态
        current_rpt_ena = False
        detail = self.get_rcb_detail(rcb_ref)
        if detail:
            current_rpt_ena = bool(detail.get("rpt_ena", False))

        if rpt_ena != current_rpt_ena:
            # RptEna 状态变化: 仅设置开关，不碰 TrgOps/OptFields
            if rpt_ena:
                return self._enable_report(rcb_ref, on_report=on_report)
            else:
                return self._disable_report(rcb_ref)

        # RptEna 状态不变: 仅写入 TrgOps/OptFields
        if current_rpt_ena:
            # 报告使能时无法修改属性，跳过
            log.info(f"报告已使能，跳过配置写入: {rcb_ref}")
            return True

        # 报告禁用时写入 TrgOps/OptFields
        if trg_ops is not None or opt_fields is not None:
            return self._set_config(rcb_ref, trg_ops, opt_fields)

        return True

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
        try:
            detail = self.get_rcb_detail(rcb_ref)
            if detail:
                rpt_id = str(detail.get("rpt_id", "") or "")
                log.info(f"_enable_report: 读取 RptId: {rcb_ref}, rpt_id={rpt_id!r}")
        except Exception as e:
            log.warning(f"_enable_report: 读取 RptId 失败: {rcb_ref}, {e}")

        callback_ok = ReportCallbackHandler.install(
            self._connection,
            rcb_ref,
            on_report=on_report,
            rcb_type=rcb_type,
            rpt_id=rpt_id,
        )
        if not callback_ok:
            log.warning(f"install report callback failed: {rcb_ref}")
            return False

        if rcb_type == "BRCB":
            success = BrcbHandler.set_rpt_ena(self._connection, rcb_ref, True)
        else:
            success = UrcbHandler.set_rpt_ena(self._connection, rcb_ref, True)

        if not success:
            log.warning(f"set RptEna=True failed: {rcb_ref}")
            ReportCallbackHandler.uninstall(self._connection, rcb_ref)
            return False

        log.info(f"report enabled: {rcb_ref}")
        return True

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

        time.sleep(0.1)

        try:
            ReportCallbackHandler.uninstall(self._connection, rcb_ref)
        except Exception as e:
            log.error(f"uninstall report callback failed: {rcb_ref}, {e}")

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
        """触发通用查询 (GI)，立即生成一次完整报告

        Args:
            rcb_ref: RCB 引用路径

        Returns:
            bool 是否成功
        """
        if not self._connection or not self._connection.is_connected:
            return False

        rcb_type = self._infer_rcb_type(rcb_ref)
        if rcb_type == "BRCB":
            return BrcbHandler.trigger_gi(self._connection, rcb_ref)
        else:
            return UrcbHandler.trigger_gi(self._connection, rcb_ref)

    # ==================== 报告数据查询 ====================

    def get_report_data(self, rcb_ref: str, limit: int = 100) -> list[dict[str, Any]]:
        """获取指定 RCB 最近接收的报告数据

        Args:
            rcb_ref: RCB 引用路径
            limit: 最多返回条数

        Returns:
            报告数据字典列表
        """
        data = ReportCallbackHandler.get_cache(rcb_ref)
        if limit > 0:
            data = data[-limit:]
        return data

    def clear_report_data(self, rcb_ref: str) -> None:
        """清除指定 RCB 的缓存数据"""
        ReportCallbackHandler.clear_cache(rcb_ref)

    # ==================== 状态查询 ====================

    def list_active_reports(self) -> list[dict[str, Any]]:
        """列出当前活跃 (已使能) 的报告订阅

        Returns:
            活跃报告信息列表
        """
        return ReportCallbackHandler.get_active_rcbs()

    def is_active(self, rcb_ref: str) -> bool:
        """检查指定 RCB 是否处于活跃状态"""
        return ReportCallbackHandler.is_active(rcb_ref)

    def get_rcb_detail(self, rcb_ref: str) -> dict[str, Any] | None:
        """获取单个 RCB 的详细信息

        Args:
            rcb_ref: RCB 引用路径

        Returns:
            RCB 详细信息字典，失败返回 None
        """
        if not self._connection or not self._connection.is_connected:
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
        if not self._connection or not self._connection.connection:
            return []
        conn = self._connection.connection
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
                log.debug(f"LD={ld} 下发现 LN: {ln_list}")
                return ln_list
        except Exception as e:
            log.debug(f"浏览 LN 失败: {ld}, {e}")
        return []
