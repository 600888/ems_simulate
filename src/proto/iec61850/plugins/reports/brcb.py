"""BRCB (缓冲报告控制块) 操作封装

BRCB 与 URCB 的主要区别:
- BRCB 在通信中断时缓存报告事件，恢复后补发
- BRCB 有 entryId / timeOfEntry / purgeBuf 等缓冲特有属性
"""

import contextlib
import datetime

from ...defs.constants import HAS_IEC61850
from ...defs.types import OptFields, RCBInfo, TrgOps
from ...log import log

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class BrcbHandler:
    """BRCB (缓冲报告控制块) 操作"""

    # RCB changes 位掩码常量 (与 libiec61850 RCB_ELEMENT_* 一致)
    RCB_RPT_ID = 1
    RCB_RPT_ENA = 2
    RCB_DAT_SET_REF = 8
    RCB_CONF_REV = 16
    RCB_OPT_FLDS = 32
    RCB_BUF_TIME = 64
    RCB_TRG_OPS = 256
    RCB_GI = 1024
    RCB_PURGE_BUF = 2048
    RCB_ENTRY_ID = 4096
    RCB_TIME_OF_ENTRY = 8192

    @staticmethod
    def _normalize_ref(rcb_ref: str) -> str:
        """规范化 BRCB 引用, 插入 FC 段 .BR.

        libiec61850 的 getRCBValues/create 要求引用形如 LD/LN.BR.rcbName。
        发现得到的裸引用 LD/LN.rcbName 缺少 FC 段, 会导致 error=3 (OBJECT_NOT_FOUND)。
        """
        if not rcb_ref or "." not in rcb_ref or "/" not in rcb_ref:
            return rcb_ref
        ln_part, rcb_name = rcb_ref.rsplit(".", 1)
        if ln_part.endswith(".BR") or ln_part.endswith(".RP"):
            return rcb_ref
        return f"{ln_part}.BR.{rcb_name}"

    @staticmethod
    def _normalize_mms_ref(rcb_ref: str) -> str:
        """Convert RCB ref to MMS report-handler format: LD/LN$BR$name."""
        if not rcb_ref or "/" not in rcb_ref:
            return rcb_ref
        if "$" in rcb_ref:
            return rcb_ref
        if "." not in rcb_ref:
            return rcb_ref
        ln_part, rcb_name = rcb_ref.rsplit(".", 1)
        if ln_part.endswith(".BR") or ln_part.endswith(".RP"):
            return rcb_ref.replace(".", "$")
        return f"{ln_part}$BR${rcb_name}"

    @staticmethod
    def _extract_error(result) -> int:
        return (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result

    @staticmethod
    def _trigger_gi_direct(conn, rcb_ref: str) -> bool:
        """Use libiec61850's dedicated GI API when available."""
        if not hasattr(iec61850, "IedConnection_triggerGIReport"):
            return False

        refs = []
        for ref in (BrcbHandler._normalize_mms_ref(rcb_ref), BrcbHandler._normalize_ref(rcb_ref), rcb_ref):
            if ref and ref not in refs:
                refs.append(ref)

        for ref in refs:
            try:
                result = iec61850.IedConnection_triggerGIReport(conn, ref)
                error = BrcbHandler._extract_error(result)
                if error == iec61850.IED_ERROR_OK:
                    log.info(f"BRCB GI direct trigger ok: {rcb_ref} (ref={ref})")
                    return True
                log.debug(f"BRCB GI direct trigger failed: ref={ref}, error={error}")
            except Exception as e:
                log.debug(f"BRCB GI direct trigger exception: ref={ref}, {e}")
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
        """获取 BRCB 所有属性值

        Args:
            connection: Iec61850Connection 实例
            rcb_ref: RCB 引用路径, 如 "LD0/LLN0.brcb01"

        Returns:
            RCBInfo 对象, 失败返回 None
        """
        if not HAS_IEC61850:
            return None
        conn = connection.connection
        if not conn:
            log.warning(f"获取 BRCB 值失败: 连接不可用, ref={rcb_ref}")
            return None

        try:
            rcb = BrcbHandler._create_rcb_block(BrcbHandler._normalize_ref(rcb_ref))
            if not rcb:
                log.warning(f"ClientReportControlBlock_create 失败: {rcb_ref}")
                return None

            try:
                result = iec61850.IedConnection_getRCBValues(conn, BrcbHandler._normalize_ref(rcb_ref), rcb)
                error = (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result

                if error != iec61850.IED_ERROR_OK:
                    log.warning(f"获取 BRCB 值失败: ref={rcb_ref}, error={error}")
                    return None

                # 提取属性值
                rcb_info = BrcbHandler._parse_rcb(rcb, rcb_ref, "BRCB")
                return rcb_info
            finally:
                with contextlib.suppress(Exception):
                    iec61850.ClientReportControlBlock_destroy(rcb)
        except Exception as e:
            log.error(f"获取 BRCB 值异常: {rcb_ref}, {e}")
            return None

    @staticmethod
    def set_rpt_ena(
        connection, rcb_ref: str, enable: bool, trg_ops: TrgOps | None = None, opt_fields: OptFields | None = None
    ) -> bool:
        """设置 BRCB 的 RptEna 及相关属性

        Args:
            connection: Iec61850Connection 实例
            rcb_ref: RCB 引用路径
            enable: True=使能, False=禁用
            trg_ops: 触发选项 (使能时设置)
            opt_fields: 可选字段 (使能时设置)

        Returns:
            bool 是否成功
        """
        if not HAS_IEC61850:
            return False
        conn = connection.connection
        if not conn:
            log.warning(f"设置 BRCB RptEna 失败: 连接不可用, ref={rcb_ref}")
            return False

        try:
            nref = BrcbHandler._normalize_ref(rcb_ref)
            rcb = BrcbHandler._create_rcb_block(nref)
            if not rcb:
                return False

            try:
                # 先读取当前值
                result = iec61850.IedConnection_getRCBValues(conn, nref, rcb)
                error = (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result
                if error != iec61850.IED_ERROR_OK:
                    log.warning(f"设置 BRCB RptEna 前读取失败: ref={rcb_ref}, error={error}")
                    return False

                changes = 0

                # 设置 RptEna
                iec61850.ClientReportControlBlock_setRptEna(rcb, enable)
                changes |= BrcbHandler.RCB_RPT_ENA

                if trg_ops:
                    # 设置 TrgOps
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
                    changes |= BrcbHandler.RCB_TRG_OPS

                if opt_fields:
                    # 设置 OptFields
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
                    if opt_fields.entry_id:
                        opt_flds_val |= 0x20
                    if opt_fields.config_ref:
                        opt_flds_val |= 0x40
                    if opt_fields.buf_ovfl:
                        opt_flds_val |= 0x80
                    iec61850.ClientReportControlBlock_setOptFlds(rcb, opt_flds_val)
                    changes |= BrcbHandler.RCB_OPT_FLDS

                # 写回服务器
                result = iec61850.IedConnection_setRCBValues(conn, rcb, changes, True)
                set_error = (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result

                if set_error != iec61850.IED_ERROR_OK:
                    log.warning(f"设置 BRCB 值失败: ref={rcb_ref}, error={set_error}")
                    return False

                log.info(f"BRCB RptEna 已{'使能' if enable else '禁用'}: {rcb_ref}")
                return True
            finally:
                with contextlib.suppress(Exception):
                    iec61850.ClientReportControlBlock_destroy(rcb)
        except Exception as e:
            log.error(f"设置 BRCB RptEna 异常: {rcb_ref}, {e}")
            return False

    @staticmethod
    def trigger_gi(connection, rcb_ref: str) -> bool:
        """触发 BRCB 的通用查询 (GI)

        设置 GI=True 后服务器立即生成一次完整报告。
        GI 位是自复位的 (self-clearing), 设置后自动清零。
        GI 只需要写 GI=True, 不需要先 getRCBValues。报告已使能时,
        预读 RCB 可能与接收线程/报告回调互相等待导致进程卡死。
        这里也不使用 setRCBValuesAsync, 避免异步请求返回后继续访问
        已 destroy 的 ClientReportControlBlock。
        """
        if not HAS_IEC61850:
            return False
        conn = connection.connection
        if not conn:
            return False

        from .callback import ReportCallbackHandler

        ReportCallbackHandler.mark_pending_gi(rcb_ref)
        log.info(f"BRCB trigger_gi 开始: rcb_ref={rcb_ref}")

        if BrcbHandler._trigger_gi_direct(conn, rcb_ref):
            return True

        try:
            nref = BrcbHandler._normalize_ref(rcb_ref)
            rcb = BrcbHandler._create_rcb_block(nref)
            if not rcb:
                log.warning(f"BRCB GI 创建 rcb 失败: {rcb_ref}")
                return False

            try:
                iec61850.ClientReportControlBlock_setGI(rcb, True)
                log.info(f"BRCB GI 写入开始: ref={rcb_ref}, nref={nref}")
                result = iec61850.IedConnection_setRCBValues(conn, rcb, BrcbHandler.RCB_GI, True)
                set_error = (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result

                if set_error != iec61850.IED_ERROR_OK:
                    log.warning(f"BRCB GI 触发失败: ref={rcb_ref}, error={set_error}")
                    return False

                log.info(f"BRCB GI 已触发: {rcb_ref}")
                return True
            finally:
                with contextlib.suppress(Exception):
                    iec61850.ClientReportControlBlock_destroy(rcb)
        except Exception as e:
            log.error(f"BRCB GI 触发异常: {rcb_ref}, {e}")
            return False

    @staticmethod
    def disable_direct(connection, rcb_ref: str) -> bool:
        """直接禁用 BRCB: 仅写 RptEna=False，不读不预约"""
        if not HAS_IEC61850:
            return False
        conn = connection.connection
        if not conn:
            return False

        try:
            nref = BrcbHandler._normalize_ref(rcb_ref)
            rcb = BrcbHandler._create_rcb_block(nref)
            if not rcb:
                return False

            try:
                iec61850.ClientReportControlBlock_setRptEna(rcb, False)
                result = iec61850.IedConnection_setRCBValues(conn, rcb, BrcbHandler.RCB_RPT_ENA, True)
                set_error = (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result

                if set_error != iec61850.IED_ERROR_OK:
                    log.warning(f"BRCB 直接禁用失败: ref={rcb_ref}, error={set_error}")
                    return False

                log.info(f"BRCB RptEna 已禁用 (直接): {rcb_ref}")
                return True
            finally:
                with contextlib.suppress(Exception):
                    iec61850.ClientReportControlBlock_destroy(rcb)
        except Exception as e:
            log.error(f"BRCB 直接禁用异常: {rcb_ref}, {e}")
            return False

    @staticmethod
    def purge_buffer(connection, rcb_ref: str) -> bool:
        """清除 BRCB 缓冲队列"""
        if not HAS_IEC61850:
            return False
        conn = connection.connection
        if not conn:
            return False

        try:
            nref = BrcbHandler._normalize_ref(rcb_ref)
            rcb = BrcbHandler._create_rcb_block(nref)
            if not rcb:
                return False

            try:
                result = iec61850.IedConnection_getRCBValues(conn, nref, rcb)
                error = (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result
                if error != iec61850.IED_ERROR_OK:
                    return False

                iec61850.ClientReportControlBlock_setPurgeBuf(rcb, True)
                result = iec61850.IedConnection_setRCBValues(conn, rcb, BrcbHandler.RCB_PURGE_BUF, True)
                set_error = (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result

                if set_error != iec61850.IED_ERROR_OK:
                    log.warning(f"BRCB 清除缓冲失败: ref={rcb_ref}, error={set_error}")
                    return False

                log.info(f"BRCB 缓冲已清除: {rcb_ref}")
                return True
            finally:
                with contextlib.suppress(Exception):
                    iec61850.ClientReportControlBlock_destroy(rcb)
        except Exception as e:
            log.error(f"BRCB 清除缓冲异常: {rcb_ref}, {e}")
            return False

    @staticmethod
    def _parse_rcb(rcb, rcb_ref: str, rcb_type: str) -> RCBInfo:
        """从 ClientReportControlBlock 解析 RCBInfo"""
        info = RCBInfo(
            name=rcb_ref.split(".")[-1] if "." in rcb_ref else rcb_ref,
            ref=rcb_ref,
            rcb_type=rcb_type,
        )

        # 解析 LD/LN
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
            info.buf_time = int(iec61850.ClientReportControlBlock_getBufTm(rcb))

        try:
            entry_id = iec61850.ClientReportControlBlock_getEntryId(rcb)
            if entry_id:
                info.entry_id = bytes(entry_id)
        except Exception:
            pass

        with contextlib.suppress(Exception):
            time_ms = int(iec61850.ClientReportControlBlock_getEntryTime(rcb))
            if time_ms > 0:
                info.time_of_entry = datetime.datetime.fromtimestamp(time_ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S")

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
                entry_id=bool(opt_val & 0x20),
                config_ref=bool(opt_val & 0x40),
                buf_ovfl=bool(opt_val & 0x80),
            )
        except Exception:
            pass

        # sq_num
        with contextlib.suppress(Exception):
            info.sq_num = int(iec61850.ClientReportControlBlock_getSqNum(rcb))

        return info
