"""URCB (非缓冲报告控制块) 操作封装

URCB 与 BRCB 的区别:
- URCB 不缓冲报告事件，通信中断时事件丢失
- URCB 无 entryId / timeOfEntry / purgeBuf 属性
- URCB 有 intgPeriod (完整性周期) 属性
"""

import contextlib

from ...core.mms_value import mms_value_to_python
from ...defs.constants import HAS_IEC61850
from ...defs.types import OptFields, RCBInfo, TrgOps
from ...log import log

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class UrcbHandler:
    """URCB (非缓冲报告控制块) 操作"""

    # RCB changes 位掩码常量 (与 libiec61850 RCB_ELEMENT_* 一致)
    RCB_RPT_ID = 1
    RCB_RPT_ENA = 2
    RCB_RESV = 4
    RCB_DAT_SET_REF = 8
    RCB_CONF_REV = 16
    RCB_OPT_FLDS = 32
    RCB_TRG_OPS = 256
    RCB_INTG_PD = 512
    RCB_GI = 1024

    @staticmethod
    def _normalize_ref(rcb_ref: str) -> str:
        """规范化 URCB 引用, 插入 FC 段 .RP.

        libiec61850 的 getRCBValues/create 要求引用形如 LD/LN.RP.rcbName。
        发现得到的裸引用 LD/LN.rcbName 缺少 FC 段, 会导致 error=3 (OBJECT_NOT_FOUND)。
        """
        if not rcb_ref or "." not in rcb_ref or "/" not in rcb_ref:
            return rcb_ref
        ln_part, rcb_name = rcb_ref.rsplit(".", 1)
        if rcb_name in ("BR", "RP"):  # 已含 FC 段
            return rcb_ref
        return f"{ln_part}.RP.{rcb_name}"

    @staticmethod
    def _normalize_mms_ref(rcb_ref: str) -> str:
        """Convert RCB ref to MMS report-handler format: LD/LN$RP$name."""
        if not rcb_ref or "/" not in rcb_ref:
            return rcb_ref
        if "$" in rcb_ref:
            return rcb_ref
        if "." not in rcb_ref:
            return rcb_ref
        ln_part, rcb_name = rcb_ref.rsplit(".", 1)
        if rcb_name in ("BR", "RP"):
            return rcb_ref.replace(".", "$")
        return f"{ln_part}$RP${rcb_name}"

    @staticmethod
    def _extract_error(result) -> int:
        return (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result

    @staticmethod
    def _trigger_gi_direct(conn, rcb_ref: str) -> bool:
        """Use libiec61850's dedicated GI API when available."""
        if not hasattr(iec61850, "IedConnection_triggerGIReport"):
            return False

        refs = []
        for ref in (UrcbHandler._normalize_mms_ref(rcb_ref), UrcbHandler._normalize_ref(rcb_ref), rcb_ref):
            if ref and ref not in refs:
                refs.append(ref)

        for ref in refs:
            try:
                result = iec61850.IedConnection_triggerGIReport(conn, ref)
                error = UrcbHandler._extract_error(result)
                if error == iec61850.IED_ERROR_OK:
                    log.info(f"URCB GI direct trigger ok: {rcb_ref} (ref={ref})")
                    return True
                log.debug(f"URCB GI direct trigger failed: ref={ref}, error={error}")
            except Exception as e:
                log.debug(f"URCB GI direct trigger exception: ref={ref}, {e}")
        return False

    @staticmethod
    def _create_rcb_block(rcb_ref: str = ""):
        """创建 ClientReportControlBlock"""
        if not HAS_IEC61850 or not rcb_ref:
            return None
        try:
            rcb = iec61850.ClientReportControlBlock_create(rcb_ref)
            if rcb is not None:
                return rcb
        except Exception as e:
            log.debug(f"_create_rcb_block 失败: {e}, ref={rcb_ref}")
        return None

    @staticmethod
    def get_rcb_values(connection, rcb_ref: str) -> RCBInfo | None:
        """获取 URCB 所有属性值

        Args:
            connection: Iec61850Connection 实例
            rcb_ref: RCB 引用路径, 如 "LD0/LLN0.urcb01"

        Returns:
            RCBInfo 对象, 失败返回 None
        """
        if not HAS_IEC61850:
            return None
        conn = connection.connection
        if not conn:
            log.warning(f"获取 URCB 值失败: 连接不可用, ref={rcb_ref}")
            return None

        try:
            rcb = UrcbHandler._create_rcb_block(UrcbHandler._normalize_ref(rcb_ref))
            if not rcb:
                log.warning(f"ClientReportControlBlock_create 失败: {rcb_ref}")
                return None

            try:
                result = iec61850.IedConnection_getRCBValues(conn, UrcbHandler._normalize_ref(rcb_ref), rcb)
                error = (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result

                if error != iec61850.IED_ERROR_OK:
                    log.warning(f"获取 URCB 值失败: ref={rcb_ref}, error={error}")
                    return None

                rcb_info = UrcbHandler._parse_rcb(rcb, rcb_ref, "URCB")
                return rcb_info
            finally:
                with contextlib.suppress(Exception):
                    iec61850.ClientReportControlBlock_destroy(rcb)
        except Exception as e:
            log.error(f"获取 URCB 值异常: {rcb_ref}, {e}")
            return None

    @staticmethod
    def set_rpt_ena(
        connection,
        rcb_ref: str,
        enable: bool,
        trg_ops: TrgOps | None = None,
        opt_fields: OptFields | None = None,
        intg_period: int = 0,
    ) -> bool:
        """设置 URCB 的 RptEna 及相关属性

        URCB 不需要 Resv 预约机制 (BRCB 才需要)，直接读写 RptEna 即可。

        Args:
            connection: Iec61850Connection 实例
            rcb_ref: RCB 引用路径
            enable: True=使能, False=禁用
            trg_ops: 触发选项 (使能时设置)
            opt_fields: 可选字段 (使能时设置)
            intg_period: 完整性周期 (ms), 仅 URCB

        Returns:
            bool 是否成功
        """
        if not HAS_IEC61850:
            return False
        conn = connection.connection
        if not conn:
            log.warning(f"设置 URCB RptEna 失败: 连接不可用, ref={rcb_ref}")
            return False

        try:
            nref = UrcbHandler._normalize_ref(rcb_ref)
            rcb = UrcbHandler._create_rcb_block(nref)
            if not rcb:
                return False

            try:
                # 先读取当前值
                result = iec61850.IedConnection_getRCBValues(conn, nref, rcb)
                error = (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result
                if error != iec61850.IED_ERROR_OK:
                    log.warning(f"设置 URCB RptEna 前读取失败: ref={rcb_ref}, error={error}")
                    return False

                # 读取当前 RptEna 状态
                current_rpt_ena = False
                with contextlib.suppress(Exception):
                    current_rpt_ena = bool(iec61850.ClientReportControlBlock_getRptEna(rcb))

                # 幂等保护: 已处于目标状态且无属性需要修改则直接返回成功
                has_config = (trg_ops is not None) or (opt_fields is not None) or intg_period > 0
                if enable and current_rpt_ena and not has_config:
                    log.info(f"URCB 已处于使能状态，跳过: {rcb_ref}")
                    return True
                if (not enable) and (not current_rpt_ena) and not has_config:
                    log.info(f"URCB 已处于禁用状态，跳过: {rcb_ref}")
                    return True

                # 设置 RptEna + TrgOps + OptFields (URCB 无需 Resv 预约)
                changes = 0
                iec61850.ClientReportControlBlock_setRptEna(rcb, enable)
                changes |= UrcbHandler.RCB_RPT_ENA

                if trg_ops:
                    trg_opts_val = 0
                    if trg_ops.dchg:
                        trg_opts_val |= 0x01
                    if trg_ops.qchg:
                        trg_opts_val |= 0x02
                    if trg_ops.dupd:
                        trg_opts_val |= 0x04
                    if trg_ops.period:
                        trg_opts_val |= 0x08
                    if trg_ops.gi:
                        trg_opts_val |= 0x10
                    iec61850.ClientReportControlBlock_setTrgOps(rcb, trg_opts_val)
                    changes |= UrcbHandler.RCB_TRG_OPS

                if opt_fields:
                    opt_flds_val = 0
                    if opt_fields.seq_num:
                        opt_flds_val |= 0x01
                    if opt_fields.time_stamp:
                        opt_flds_val |= 0x02
                    if opt_fields.reason_code:
                        opt_flds_val |= 0x04
                    if opt_fields.data_set:
                        opt_flds_val |= 0x08
                    if opt_fields.data_ref:
                        opt_flds_val |= 0x10
                    iec61850.ClientReportControlBlock_setOptFlds(rcb, opt_flds_val)
                    changes |= UrcbHandler.RCB_OPT_FLDS

                if intg_period > 0:
                    iec61850.ClientReportControlBlock_setIntgPd(rcb, intg_period)
                    changes |= UrcbHandler.RCB_INTG_PD

                result = iec61850.IedConnection_setRCBValues(conn, rcb, changes, True)
                set_error = (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result

                if set_error != iec61850.IED_ERROR_OK:
                    log.warning(f"设置 URCB 值失败: ref={rcb_ref}, error={set_error}")
                    return False

                log.info(f"URCB RptEna 已{'使能' if enable else '禁用'}: {rcb_ref}")
                return True
            finally:
                with contextlib.suppress(Exception):
                    iec61850.ClientReportControlBlock_destroy(rcb)
        except Exception as e:
            log.error(f"设置 URCB RptEna 异常: {rcb_ref}, {e}")
            return False

    @staticmethod
    def disable_direct(connection, rcb_ref: str) -> bool:
        """直接禁用 URCB，仅设置 RptEna=False，不涉及其他属性

        URCB 禁用逻辑非常简单，不需要 Resv、不需要读取当前值、
        不需要处理 TrgOps/OptFields，直接写 RptEna=False 即可。

        Args:
            connection: Iec61850Connection 实例
            rcb_ref: RCB 引用路径

        Returns:
            bool 是否成功
        """
        if not HAS_IEC61850:
            return False
        conn = connection.connection
        if not conn:
            log.warning(f"URCB 禁用失败: 连接不可用, ref={rcb_ref}")
            return False

        try:
            nref = UrcbHandler._normalize_ref(rcb_ref)
            rcb = UrcbHandler._create_rcb_block(nref)
            if not rcb:
                return False

            try:
                iec61850.ClientReportControlBlock_setRptEna(rcb, False)
                result = iec61850.IedConnection_setRCBValues(conn, rcb, UrcbHandler.RCB_RPT_ENA, True)
                set_error = (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result

                if set_error != iec61850.IED_ERROR_OK:
                    log.warning(f"URCB 禁用失败: ref={rcb_ref}, error={set_error}")
                    return False

                log.info(f"URCB 已禁用: {rcb_ref}")
                return True
            finally:
                with contextlib.suppress(Exception):
                    iec61850.ClientReportControlBlock_destroy(rcb)
        except Exception as e:
            log.error(f"URCB 禁用异常: {rcb_ref}, {e}")
            return False

    @staticmethod
    def trigger_gi(connection, rcb_ref: str) -> bool:
        """触发 URCB 的通用查询 (GI)"""
        if not HAS_IEC61850:
            return False
        conn = connection.connection
        if not conn:
            return False

        try:
            if UrcbHandler._trigger_gi_direct(conn, rcb_ref):
                return True

            nref = UrcbHandler._normalize_ref(rcb_ref)
            rcb = UrcbHandler._create_rcb_block(nref)
            if not rcb:
                return False

            try:
                result = iec61850.IedConnection_getRCBValues(conn, nref, rcb)
                error = (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result
                if error != iec61850.IED_ERROR_OK:
                    return False

                iec61850.ClientReportControlBlock_setGI(rcb, True)
                result = iec61850.IedConnection_setRCBValues(conn, rcb, UrcbHandler.RCB_GI, True)
                set_error = (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result

                if set_error != iec61850.IED_ERROR_OK:
                    log.warning(f"URCB GI 触发失败: ref={rcb_ref}, error={set_error}")
                    return False

                log.info(f"URCB GI 已触发: {rcb_ref}")
                return True
            finally:
                with contextlib.suppress(Exception):
                    iec61850.ClientReportControlBlock_destroy(rcb)
        except Exception as e:
            log.error(f"URCB GI 触发异常: {rcb_ref}, {e}")
            return False

    @staticmethod
    def _parse_rcb(rcb, rcb_ref: str, rcb_type: str) -> RCBInfo:
        """从 ClientReportControlBlock 解析 RCBInfo"""
        info = RCBInfo(
            name=rcb_ref.split(".")[-1] if "." in rcb_ref else rcb_ref,
            ref=rcb_ref,
            rcb_type=rcb_type,
        )

        if rcb_ref and "/" in rcb_ref:
            parts = rcb_ref.split("/", 1)
            info.ld = parts[0]
            ln_part = parts[1].split(".")[0] if "." in parts[1] else parts[1]
            info.ln = ln_part

        with contextlib.suppress(Exception):
            info.rpt_id = str(iec61850.ClientReportControlBlock_getRptId(rcb))

        with contextlib.suppress(Exception):
            info.rpt_ena = bool(iec61850.ClientReportControlBlock_getRptEna(rcb))

        try:
            ds_ref = iec61850.ClientReportControlBlock_getDataSetReference(rcb)
            if ds_ref:
                info.data_set_ref = str(ds_ref)
        except Exception:
            pass

        with contextlib.suppress(Exception):
            info.conf_rev = int(iec61850.ClientReportControlBlock_getConfRev(rcb))

        with contextlib.suppress(Exception):
            info.intg_period = int(iec61850.ClientReportControlBlock_getIntgPd(rcb))

        # 解析 TrgOps
        try:
            trg_val = int(iec61850.ClientReportControlBlock_getTrgOps(rcb))
            info.trg_ops = TrgOps(
                dchg=bool(trg_val & 0x01),
                qchg=bool(trg_val & 0x02),
                dupd=bool(trg_val & 0x04),
                period=bool(trg_val & 0x08),
                gi=bool(trg_val & 0x10),
            )
        except Exception:
            pass

        # 解析 OptFields
        try:
            opt_val = int(iec61850.ClientReportControlBlock_getOptFlds(rcb))
            info.opt_fields = OptFields(
                seq_num=bool(opt_val & 0x01),
                time_stamp=bool(opt_val & 0x02),
                reason_code=bool(opt_val & 0x04),
                data_set=bool(opt_val & 0x08),
                data_ref=bool(opt_val & 0x10),
            )
        except Exception:
            pass

        # sq_num
        with contextlib.suppress(Exception):
            info.sq_num = int(iec61850.ClientReportControlBlock_getSqNum(rcb))

        # owner (URCB only)
        try:
            owner_val = iec61850.ClientReportControlBlock_getOwner(rcb)
            if owner_val:
                info.owner = str(mms_value_to_python(owner_val))
        except Exception:
            pass

        # resv (URCB only)
        with contextlib.suppress(Exception):
            info.resv = bool(iec61850.ClientReportControlBlock_getResv(rcb))

        return info
