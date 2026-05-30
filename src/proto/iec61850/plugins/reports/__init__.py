"""Reports 插件 - 报告控制块 (BRCB/URCB) 操作

管理 BRCB/URCB 报告控制块的发现、使能/禁用、GI 触发、
回调注册和报告数据缓存等完整生命周期。
"""

import datetime
from typing import Any, Dict, List, Optional, Callable

from ..base import Iec61850Plugin
from ...defs.constants import HAS_IEC61850, AcsiClass
from ...defs.types import RCBInfo, TrgOps, OptFields, ReportDataEntry
from ...core.linked_list import get_list_from_linked_list
from ...log import log

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850

from .brcb import BrcbHandler
from .urcb import UrcbHandler
from .callback import ReportCallbackHandler


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

    # 回退探测: 常见的 RCB 名称模式 (brcb01..brcb20, urcb01..urcb20)
    _FALLBACK_RCB_NAMES = (
        [f"brcb{i:02d}" for i in range(1, 21)] +
        [f"urcb{i:02d}" for i in range(1, 21)]
    )

    def discover_rcbs(self, ld: str = "", ln: str = "") -> List[Dict[str, Any]]:
        """发现报告控制块 (BRCB 和 URCB)

        发现策略（两级）:
        1. 通过 IedConnection_getLogicalNodeDirectory(acsi_class) 发现 BRCB/URCB
        2. 回退: 探测常见 RCB 名称 (brcb01..brcb20, urcb01..urcb20) 的 RptEna 属性

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

                # 3. 策略一: 通过 ACSI 目录发现 BRCB 和 URCB
                rcbs_found = self._discover_rcbs_via_directory(conn, ln_ref, ld_name, ln_name)

                # 4. 策略二: 如果目录发现失败或无结果, 回退到探测法
                if not rcbs_found:
                    rcbs_found = self._discover_rcbs_via_probe(conn, ln_ref, ld_name, ln_name)

                all_rcbs.extend(rcbs_found)

        log.info(f"RCB 发现完成, 共发现 {len(all_rcbs)} 个报告控制块")
        return all_rcbs

    def _discover_rcbs_via_directory(self, conn, ln_ref: str,
                                      ld_name: str, ln_name: str) -> List[Dict]:
        """策略一: 通过 ACSI 目录发现 RCB"""
        rcbs = []
        for _rcb_type, acsi_class in [("URCB", AcsiClass.URCB), ("BRCB", AcsiClass.BRCB)]:
            try:
                result = iec61850.IedConnection_getLogicalNodeDirectory(
                    conn, ln_ref, acsi_class
                )
                rcb_names_raw = result[0] if isinstance(result, (list, tuple)) else result
                error = result[1] if isinstance(result, (list, tuple)) else 0

                if error != iec61850.IED_ERROR_OK:
                    log.debug(f"ACSI目录法 获取 {_rcb_type} 失败: {ln_ref}, error={error}")
                    continue

                if rcb_names_raw is None:
                    continue

                rcb_name_list = get_list_from_linked_list(rcb_names_raw)

                if rcb_name_list:
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

    def _discover_rcbs_via_probe(self, conn, ln_ref: str,
                                  ld_name: str, ln_name: str) -> List[Dict]:
        """策略二: 回退 - 探测 RptEna 属性发现 RCB

        当服务端不支持 ACSI 目录法时，通过尝试读取
        LLN0.RP.brcb01.RptEna 等属性是否存在来探测 RCB。
        """
        rcbs = []
        fc_rp = self._connection.get_fc_value("RP") if hasattr(self._connection, 'get_fc_value') else None
        fc_br = getattr(iec61850, 'IEC61850_FC_BR', None) if HAS_IEC61850 else None

        # 备用: 使用 getLogicalNodeDirectory(DATA_OBJECT) 获取所有 DO
        # 从中识别 RCB (名称以 brcb/urcb 开头)
        do_names = self._probe_do_names(conn, ln_ref)
        if not do_names:
            return rcbs

        # 过滤出 RCB 名称 (brcb/urcb 开头的 DO)
        rcb_candidates = []
        for do_name in do_names:
            lower = do_name.lower()
            if lower.startswith("brcb") or lower.startswith("urcb"):
                rcb_candidates.append(do_name)

        if not rcb_candidates:
            log.debug(f"探测法: {ln_ref} 下无 brcb/urcb 前缀的 DO")
            return rcbs

        log.info(f"探测法: {ln_ref} 下发现 {len(rcb_candidates)} 个 RCB 候选: {rcb_candidates}")

        for rcb_name in rcb_candidates:
            rcb_type = "BRCB" if rcb_name.lower().startswith("brcb") else "URCB"
            guess_fc = "RP" if rcb_type == "URCB" else "BR"
            rcb_ref = f"{ln_ref}.{rcb_name}"

            # 验证: 尝试读取 rptEna 属性 (FC=RP 或 BR)
            if self._verify_rcb_by_rptena(conn, rcb_ref, guess_fc):
                rcb_info = self._get_rcb_info(rcb_ref, rcb_type, ld_name, ln_name)
                rcbs.append(rcb_info)
                log.info(f"探测法发现 {rcb_type}: {rcb_ref}")

        return rcbs

    def _probe_do_names(self, conn, ln_ref: str) -> List[str]:
        """获取 LN 下的所有 DO 名称"""
        try:
            result = iec61850.IedConnection_getLogicalNodeDirectory(
                conn, ln_ref, AcsiClass.DATA_OBJECT
            )
            do_raw = result[0] if isinstance(result, (list, tuple)) else result
            error = result[1] if isinstance(result, (list, tuple)) else 0
            if error == iec61850.IED_ERROR_OK and do_raw:
                return get_list_from_linked_list(do_raw)
        except Exception:
            pass
        return []

    def _verify_rcb_by_rptena(self, conn, rcb_ref: str, fc: str = "RP") -> bool:
        """通过读取 RptEna 属性验证 RCB 是否存在

        RptEna 是所有 RCB 的必选属性, FC=RP (URCB) 或 BR (BRCB)。
        尝试读取成功即确认该 RCB 存在。
        """
        if not HAS_IEC61850:
            return False

        # 尝试 RP 和 BR 两种 FC
        fcs_to_try = ["RP", "BR"]
        if fc and fc in fcs_to_try:
            # 将指定 FC 放首位
            fcs_to_try.remove(fc)
            fcs_to_try.insert(0, fc)

        for fc_val in fcs_to_try:
            try:
                fc_const = self._get_fc_const(fc_val)
                if fc_const is None:
                    continue
                rpt_ena_ref = f"{rcb_ref}.RptEna"
                val = iec61850.IedConnection_readBooleanValue(conn, rpt_ena_ref, fc_const)
                if val is not None:
                    log.debug(f"验证 RCB 成功: {rcb_ref} (FC={fc_val})")
                    return True
            except Exception:
                continue

        # 也尝试直接读取 RCB 值作为最终验证
        try:
            rcb_test = iec61850.ClientReportControlBlock_create()
            if rcb_test:
                try:
                    result = iec61850.IedConnection_getRCBValues(conn, rcb_ref, rcb_test)
                    error = result[1] if isinstance(result, (list, tuple)) else result
                    if error == iec61850.IED_ERROR_OK:
                        return True
                finally:
                    try:
                        iec61850.ClientReportControlBlock_destroy(rcb_test)
                    except Exception:
                        pass
        except Exception:
            pass

        return False

    def _get_fc_const(self, fc: str):
        """获取 FC 字符串对应的 pyiec61850 常量"""
        if not HAS_IEC61850:
            return None
        try:
            fc_map = {
                "RP": iec61850.IEC61850_FC_RP,
                "BR": iec61850.IEC61850_FC_BR,
                "MX": iec61850.IEC61850_FC_MX,
                "ST": iec61850.IEC61850_FC_ST,
                "CO": iec61850.IEC61850_FC_CO,
                "CF": iec61850.IEC61850_FC_CF,
            }
            return fc_map.get(fc)
        except Exception:
            return None

    def _get_rcb_info(self, rcb_ref: str, rcb_type: str,
                       ld_name: str, ln_name: str) -> Dict[str, Any]:
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
                for field_name in ("rpt_id", "rpt_ena", "data_set_ref", "conf_rev",
                                    "buf_time", "intg_period", "trg_ops", "opt_fields"):
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
        except Exception as e:
            log.debug(f"读取 RCB 属性失败: {rcb_ref}, {e}")

        return self._rcb_info_to_dict(info)

    def _rcb_info_to_dict(self, info: RCBInfo) -> Dict[str, Any]:
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
            "purge_buf": info.purge_buf,
            "entry_id": info.entry_id.hex() if info.entry_id else None,
            "time_of_entry": info.time_of_entry,
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

    # ==================== 报告使能/禁用 ====================

    def enable_report(self, rcb_ref: str, gi: bool = True,
                      trg_ops: Optional[Dict[str, bool]] = None,
                      opt_fields: Optional[Dict[str, bool]] = None,
                      on_report: Optional[Callable[[ReportDataEntry], None]] = None) -> bool:
        """使能报告控制块

        设置 RptEna=True，配置 TrgOps/OptFields，安装报告回调。

        Args:
            rcb_ref: RCB 引用路径
            gi: 是否同时触发 GI
            trg_ops: 触发选项字典 (可选，使用默认)
            opt_fields: 可选字段字典 (可选，使用默认)
            on_report: 报告接收回调 (可选)

        Returns:
            bool 是否成功
        """
        if not self._connection or not self._connection.is_connected:
            log.warning(f"使能报告失败: 连接不可用, ref={rcb_ref}")
            return False

        # 构建 TrgOps
        trg = TrgOps()
        if trg_ops:
            trg.dchg = trg_ops.get("dchg", True)
            trg.qchg = trg_ops.get("qchg", False)
            trg.dupd = trg_ops.get("dupd", False)
            trg.period = trg_ops.get("period", False)
            trg.gi = trg_ops.get("gi", gi)

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

        # 设置 RptEna
        if rcb_type == "BRCB":
            success = BrcbHandler.set_rpt_ena(
                self._connection, rcb_ref, True, trg, opt
            )
        else:
            success = UrcbHandler.set_rpt_ena(
                self._connection, rcb_ref, True, trg, opt
            )

        if not success:
            log.warning(f"设置 RptEna 失败: {rcb_ref}")
            return False

        # 安装报告回调
        callback_ok = ReportCallbackHandler.install(
            self._connection, rcb_ref,
            on_report=on_report,
        )
        if not callback_ok:
            log.warning(f"安装报告回调失败: {rcb_ref} (RptEna 已设置)")
            # RptEna 已设置但回调安装失败，尝试回滚
            self._set_rpt_ena_raw(rcb_ref, False)
            return False

        # 可选: 触发 GI
        if gi:
            self.trigger_gi(rcb_ref)

        log.info(f"报告已使能: {rcb_ref}")
        return True

    def disable_report(self, rcb_ref: str) -> bool:
        """禁用报告控制块

        注销回调并设置 RptEna=False。

        Args:
            rcb_ref: RCB 引用路径

        Returns:
            bool 是否成功
        """
        if not self._connection or not self._connection.is_connected:
            log.warning(f"禁用报告失败: 连接不可用, ref={rcb_ref}")
            return False

        # 先注销回调
        ReportCallbackHandler.uninstall(self._connection, rcb_ref)

        # 设置 RptEna=False
        success = self._set_rpt_ena_raw(rcb_ref, False)

        if success:
            log.info(f"报告已禁用: {rcb_ref}")
        else:
            log.warning(f"设置 RptEna=False 失败: {rcb_ref} (回调已注销)")

        return success

    def _set_rpt_ena_raw(self, rcb_ref: str, enable: bool) -> bool:
        """仅设置 RptEna，不操作回调"""
        rcb_type = self._infer_rcb_type(rcb_ref)
        if rcb_type == "BRCB":
            return BrcbHandler.set_rpt_ena(self._connection, rcb_ref, enable)
        else:
            return UrcbHandler.set_rpt_ena(self._connection, rcb_ref, enable)

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

    def get_report_data(self, rcb_ref: str, limit: int = 100) -> List[Dict[str, Any]]:
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

    def list_active_reports(self) -> List[Dict[str, Any]]:
        """列出当前活跃 (已使能) 的报告订阅

        Returns:
            活跃报告信息列表
        """
        return ReportCallbackHandler.get_active_rcbs()

    def is_active(self, rcb_ref: str) -> bool:
        """检查指定 RCB 是否处于活跃状态"""
        return ReportCallbackHandler.is_active(rcb_ref)

    def get_rcb_detail(self, rcb_ref: str) -> Optional[Dict[str, Any]]:
        """获取单个 RCB 的详细信息

        Args:
            rcb_ref: RCB 引用路径

        Returns:
            RCB 详细信息字典，失败返回 None
        """
        if not self._connection or not self._connection.is_connected:
            return None

        rcb_type = self._infer_rcb_type(rcb_ref)

        rcb_name = rcb_ref.split(".")[-1] if "." in rcb_ref else rcb_ref
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

        优先通过名称前缀判断，默认返回 BRCB。
        """
        rcb_name = rcb_ref.split(".")[-1].lower() if "." in rcb_ref else rcb_ref.lower()
        if rcb_name.startswith("urcb"):
            return "URCB"
        if rcb_name.startswith("brcb"):
            return "BRCB"
        # 默认通过 AcsiClass 发现判断
        return "BRCB"

    def _browse_logical_nodes(self, ld: str) -> List[str]:
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
