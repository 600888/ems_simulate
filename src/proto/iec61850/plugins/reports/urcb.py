"""URCB (非缓冲报告控制块) 操作封装

URCB 与 BRCB 的区别:
- URCB 不缓冲报告事件，通信中断时事件丢失
- URCB 无 entryId / timeOfEntry / purgeBuf 属性
- URCB 有 intgPeriod (完整性周期) 属性
"""

from typing import Optional

from ...defs.constants import HAS_IEC61850
from ...defs.types import RCBInfo, TrgOps, OptFields
from ...log import log

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class UrcbHandler:
    """URCB (非缓冲报告控制块) 操作"""

    # RCB changes 位掩码常量
    RCB_RPT_ENA = 0x0001
    RCB_DAT_SET_REF = 0x0002
    RCB_RPT_ID = 0x0004
    RCB_CONF_REV = 0x0020
    RCB_TRG_OPS = 0x0040
    RCB_OPT_FLDS = 0x0080
    RCB_GI = 0x0800
    RCB_INTG_PD = 0x1000

    @staticmethod
    def get_rcb_values(connection, rcb_ref: str) -> Optional[RCBInfo]:
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
            rcb = iec61850.ClientReportControlBlock_create()
            if not rcb:
                log.warning(f"ClientReportControlBlock_create 失败: {rcb_ref}")
                return None

            try:
                result = iec61850.IedConnection_getRCBValues(conn, rcb_ref, rcb)
                if isinstance(result, (list, tuple)):
                    error = result[1] if len(result) > 1 else 0
                else:
                    error = result

                if error != iec61850.IED_ERROR_OK:
                    log.warning(f"获取 URCB 值失败: ref={rcb_ref}, error={error}")
                    return None

                rcb_info = UrcbHandler._parse_rcb(rcb, rcb_ref, "URCB")
                return rcb_info
            finally:
                try:
                    iec61850.ClientReportControlBlock_destroy(rcb)
                except Exception:
                    pass
        except Exception as e:
            log.error(f"获取 URCB 值异常: {rcb_ref}, {e}")
            return None

    @staticmethod
    def set_rpt_ena(connection, rcb_ref: str, enable: bool,
                    trg_ops: Optional[TrgOps] = None,
                    opt_fields: Optional[OptFields] = None,
                    intg_period: int = 0) -> bool:
        """设置 URCB 的 RptEna 及相关属性

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
            rcb = iec61850.ClientReportControlBlock_create()
            if not rcb:
                return False

            try:
                # 先读取当前值
                result = iec61850.IedConnection_getRCBValues(conn, rcb_ref, rcb)
                if isinstance(result, (list, tuple)):
                    error = result[1] if len(result) > 1 else 0
                else:
                    error = result
                if error != iec61850.IED_ERROR_OK:
                    log.warning(f"设置 URCB RptEna 前读取失败: ref={rcb_ref}, error={error}")
                    return False

                changes = 0

                # 设置 RptEna
                iec61850.ClientReportControlBlock_setRptEna(rcb, enable)
                changes |= UrcbHandler.RCB_RPT_ENA

                if enable and trg_ops:
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

                if enable and opt_fields:
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

                if enable and intg_period > 0:
                    iec61850.ClientReportControlBlock_setIntgPd(rcb, intg_period)
                    changes |= UrcbHandler.RCB_INTG_PD

                # 写回服务器
                result = iec61850.IedConnection_setRCBValues(conn, rcb_ref, rcb, changes)
                if isinstance(result, (list, tuple)):
                    set_error = result[1] if len(result) > 1 else 0
                else:
                    set_error = result

                if set_error != iec61850.IED_ERROR_OK:
                    log.warning(f"设置 URCB 值失败: ref={rcb_ref}, error={set_error}")
                    return False

                log.info(f"URCB RptEna 已{'使能' if enable else '禁用'}: {rcb_ref}")
                return True
            finally:
                try:
                    iec61850.ClientReportControlBlock_destroy(rcb)
                except Exception:
                    pass
        except Exception as e:
            log.error(f"设置 URCB RptEna 异常: {rcb_ref}, {e}")
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
            rcb = iec61850.ClientReportControlBlock_create()
            if not rcb:
                return False

            try:
                result = iec61850.IedConnection_getRCBValues(conn, rcb_ref, rcb)
                if isinstance(result, (list, tuple)):
                    error = result[1] if len(result) > 1 else 0
                else:
                    error = result
                if error != iec61850.IED_ERROR_OK:
                    return False

                iec61850.ClientReportControlBlock_setGI(rcb, True)
                result = iec61850.IedConnection_setRCBValues(
                    conn, rcb_ref, rcb, UrcbHandler.RCB_GI
                )
                if isinstance(result, (list, tuple)):
                    set_error = result[1] if len(result) > 1 else 0
                else:
                    set_error = result

                if set_error != iec61850.IED_ERROR_OK:
                    log.warning(f"URCB GI 触发失败: ref={rcb_ref}, error={set_error}")
                    return False

                log.info(f"URCB GI 已触发: {rcb_ref}")
                return True
            finally:
                try:
                    iec61850.ClientReportControlBlock_destroy(rcb)
                except Exception:
                    pass
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

        try:
            info.rpt_id = str(iec61850.ClientReportControlBlock_getRptId(rcb))
        except Exception:
            pass

        try:
            info.rpt_ena = bool(iec61850.ClientReportControlBlock_getRptEna(rcb))
        except Exception:
            pass

        try:
            ds_ref = iec61850.ClientReportControlBlock_getDataSetRef(rcb)
            if ds_ref:
                info.data_set_ref = str(ds_ref)
        except Exception:
            pass

        try:
            info.conf_rev = int(iec61850.ClientReportControlBlock_getConfRev(rcb))
        except Exception:
            pass

        try:
            info.intg_period = int(iec61850.ClientReportControlBlock_getIntgPd(rcb))
        except Exception:
            pass

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

        return info
