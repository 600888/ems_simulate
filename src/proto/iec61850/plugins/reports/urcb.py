"""URCB (非缓冲报告控制块) 操作封装

URCB 与 BRCB 的区别:
- URCB 不缓冲报告事件，通信中断时事件丢失
- URCB 无 entryId / timeOfEntry / purgeBuf 属性
- URCB 有 intgPeriod (完整性周期) 属性
"""

import contextlib

from ...core.mms_value import mms_value_to_python
from ...core.native_calls import call_gil_safe
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
    def _split_ref(rcb_ref: str) -> tuple[str, str] | None:
        """Return (LD/LN, rcbName) from dot or dollar RCB refs."""
        if not rcb_ref or "/" not in rcb_ref:
            return None
        ref = rcb_ref.replace("$", ".")
        if "." not in ref:
            return None
        ln_part, rcb_name = ref.rsplit(".", 1)
        if rcb_name in ("BR", "RP"):
            return None
        if "." in ln_part:
            maybe_ln, maybe_fc = ln_part.rsplit(".", 1)
            if maybe_fc in ("BR", "RP"):
                ln_part = maybe_ln
        return ln_part, rcb_name

    @staticmethod
    def _normalize_ref(rcb_ref: str) -> str:
        """Normalize URCB refs to libiec61850 get/set form: LD/LN.RP.rcbName."""
        parts = UrcbHandler._split_ref(rcb_ref)
        if not parts:
            return rcb_ref
        ln_part, rcb_name = parts
        return f"{ln_part}.RP.{rcb_name}"

    @staticmethod
    def _normalize_mms_ref(rcb_ref: str) -> str:
        """Convert RCB ref to MMS report-handler form: LD/LN$RP$name."""
        parts = UrcbHandler._split_ref(rcb_ref)
        if not parts:
            return rcb_ref
        ln_part, rcb_name = parts
        return f"{ln_part}$RP${rcb_name}"

    @staticmethod
    def _strip_report_instance_suffix(name: str) -> str:
        """Strip a RptEnabled instance suffix such as 01 from an RCB name."""
        if len(name) > 2 and name[-2:].isdigit():
            return name[:-2]
        return name

    @staticmethod
    def _without_instance_suffix(rcb_ref: str) -> str:
        parts = UrcbHandler._split_ref(rcb_ref)
        if not parts:
            return rcb_ref
        ln_part, rcb_name = parts
        base_name = UrcbHandler._strip_report_instance_suffix(rcb_name)
        if base_name == rcb_name:
            return rcb_ref
        return f"{ln_part}.{base_name}"

    @staticmethod
    def _candidate_refs(rcb_ref: str) -> list[str]:
        """Try the exact RCB name first, then the base name without instance suffix."""
        refs = []
        for candidate in (rcb_ref, UrcbHandler._without_instance_suffix(rcb_ref)):
            nref = UrcbHandler._normalize_ref(candidate)
            if nref and nref not in refs:
                refs.append(nref)
        return refs

    @staticmethod
    def _extract_error(result) -> int:
        return (result[1] if len(result) > 1 else 0) if isinstance(result, (list, tuple)) else result

    @staticmethod
    def _gi_attribute_refs(rcb_ref: str) -> list[str]:
        refs = []
        candidates = (UrcbHandler._without_instance_suffix(rcb_ref), rcb_ref)
        for candidate in candidates:
            parts = UrcbHandler._split_ref(candidate)
            if not parts:
                continue
            ln_part, rcb_name = parts
            for attr_ref in (f"{ln_part}.{rcb_name}.GI", f"{ln_part}.RP.{rcb_name}.GI"):
                if attr_ref not in refs:
                    refs.append(attr_ref)
        return refs

    @staticmethod
    def _error_text(error) -> str:
        if isinstance(error, int):
            with contextlib.suppress(Exception):
                return f"{error}({iec61850.IedClientError_toString(error)})"
        return str(error)

    @staticmethod
    def _trigger_gi_write_object(conn, rcb_ref: str) -> bool:
        """Trigger URCB GI by writing the RP/GI attribute directly."""
        fc_rp = getattr(iec61850, "IEC61850_FC_RP", None)
        if fc_rp is None:
            return False

        failures = []
        for attr_ref in UrcbHandler._gi_attribute_refs(rcb_ref):
            value = None
            try:
                value = iec61850.MmsValue_newBoolean(True)
                if not value:
                    failures.append(f"{attr_ref}: create-boolean-failed")
                    continue
                result = iec61850.IedConnection_writeObject(conn, attr_ref, fc_rp, value)
                error = UrcbHandler._extract_error(result)
                if error == iec61850.IED_ERROR_OK:
                    log.info(f"URCB GI 直接写属性成功: ref={rcb_ref}, attr={attr_ref}")
                    return True

                failures.append(f"{attr_ref}: {UrcbHandler._error_text(error)}")
            except Exception as e:
                failures.append(f"{attr_ref}: {e}")
            finally:
                if value is not None:
                    with contextlib.suppress(Exception):
                        iec61850.MmsValue_delete(value)

        log.warning(f"URCB GI 直接写属性失败: ref={rcb_ref}, attempts={failures}")
        return False

    @staticmethod
    def _trigger_gi_direct(conn, rcb_ref: str) -> bool:
        """Use libiec61850's dedicated GI API when available."""
        refs = []
        for nref in UrcbHandler._candidate_refs(rcb_ref):
            for ref in (UrcbHandler._normalize_mms_ref(nref), nref):
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
        """Read URCB attributes, falling back from instance refs to the base RCB ref."""
        if not HAS_IEC61850:
            return None
        conn = connection.connection
        if not conn:
            log.warning(f"获取 URCB 值失败: 连接不可用, ref={rcb_ref}")
            return None

        last_error = None
        try:
            for nref in UrcbHandler._candidate_refs(rcb_ref):
                rcb = UrcbHandler._create_rcb_block(nref)
                if not rcb:
                    log.debug(f"ClientReportControlBlock_create failed: {rcb_ref} (nref={nref})")
                    continue

                try:
                    result = call_gil_safe(iec61850, "IedConnection_getRCBValues", conn, nref, rcb)
                    error = UrcbHandler._extract_error(result)
                    if error != iec61850.IED_ERROR_OK:
                        last_error = error
                        log.debug(f"获取 URCB 值失败，尝试下一个引用: ref={rcb_ref}, nref={nref}, error={error}")
                        continue

                    if nref != UrcbHandler._normalize_ref(rcb_ref):
                        log.info(f"URCB 使用基础引用读取成功: ref={rcb_ref}, nref={nref}")
                    return UrcbHandler._parse_rcb(rcb, rcb_ref, "URCB")
                finally:
                    with contextlib.suppress(Exception):
                        iec61850.ClientReportControlBlock_destroy(rcb)

            log.debug(f"获取 URCB 值失败: ref={rcb_ref}, error={last_error}")
            return None
        except Exception as e:
            log.error(f"获取 URCB 值异常: {rcb_ref}, {e}")
            return None

    @staticmethod
    def set_rpt_id(connection, rcb_ref: str, rpt_id: str) -> bool:
        """Write a unique RptId to one disabled URCB instance.

        Unlike other URCB operations this deliberately has no base-name
        fallback: writing the base RCB would make sibling instances share the
        same RptId again.
        """
        if not HAS_IEC61850 or not rpt_id:
            return False
        conn = connection.connection
        if not conn:
            return False

        nref = UrcbHandler._normalize_ref(rcb_ref)
        rcb = UrcbHandler._create_rcb_block(nref)
        if not rcb:
            return False

        try:
            result = call_gil_safe(iec61850, "IedConnection_getRCBValues", conn, nref, rcb)
            error = UrcbHandler._extract_error(result)
            if error != iec61850.IED_ERROR_OK:
                log.warning(f"设置 URCB RptId 前读取失败: ref={rcb_ref}, error={error}")
                return False

            iec61850.ClientReportControlBlock_setRptId(rcb, rpt_id)
            result = call_gil_safe(
                iec61850,
                "IedConnection_setRCBValues",
                conn,
                rcb,
                UrcbHandler.RCB_RPT_ID,
                True,
            )
            error = UrcbHandler._extract_error(result)
            if error != iec61850.IED_ERROR_OK:
                log.warning(f"设置 URCB RptId 失败: ref={rcb_ref}, rpt_id={rpt_id!r}, error={error}")
                return False

            log.info(f"URCB RptId 已更新: ref={rcb_ref}, rpt_id={rpt_id!r}")
            return True
        except Exception as e:
            log.error(f"设置 URCB RptId 异常: ref={rcb_ref}, rpt_id={rpt_id!r}, {e}")
            return False
        finally:
            with contextlib.suppress(Exception):
                iec61850.ClientReportControlBlock_destroy(rcb)

    @staticmethod
    def set_rpt_ena(
        connection,
        rcb_ref: str,
        enable: bool,
        trg_ops: TrgOps | None = None,
        opt_fields: OptFields | None = None,
        intg_period: int = 0,
    ) -> bool:
        """Set URCB RptEna and related fields, with base-ref fallback for RptEnabled instances."""
        if not HAS_IEC61850:
            return False
        conn = connection.connection
        if not conn:
            log.warning(f"设置 URCB RptEna 失败: 连接不可用, ref={rcb_ref}")
            return False

        last_error = None
        try:
            for nref in UrcbHandler._candidate_refs(rcb_ref):
                rcb = UrcbHandler._create_rcb_block(nref)
                if not rcb:
                    continue

                try:
                    result = call_gil_safe(iec61850, "IedConnection_getRCBValues", conn, nref, rcb)
                    error = UrcbHandler._extract_error(result)
                    if error != iec61850.IED_ERROR_OK:
                        last_error = error
                        log.debug(
                            f"设置 URCB RptEna 前读取失败，尝试下一个引用: ref={rcb_ref}, nref={nref}, error={error}"
                        )
                        continue

                    current_rpt_ena = False
                    with contextlib.suppress(Exception):
                        current_rpt_ena = bool(iec61850.ClientReportControlBlock_getRptEna(rcb))

                    has_config = (trg_ops is not None) or (opt_fields is not None) or intg_period > 0
                    if enable and current_rpt_ena and not has_config:
                        log.info(f"URCB 已处于使能状态，跳过: {rcb_ref}")
                        return True
                    if (not enable) and (not current_rpt_ena) and not has_config:
                        log.info(f"URCB 已处于禁用状态，跳过: {rcb_ref}")
                        return True

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
                        if opt_fields.buf_ovfl:
                            opt_flds_val |= 0x20
                        if opt_fields.entry_id:
                            opt_flds_val |= 0x40
                        if opt_fields.config_ref:
                            opt_flds_val |= 0x80
                        iec61850.ClientReportControlBlock_setOptFlds(rcb, opt_flds_val)
                        changes |= UrcbHandler.RCB_OPT_FLDS

                    if intg_period > 0:
                        iec61850.ClientReportControlBlock_setIntgPd(rcb, intg_period)
                        changes |= UrcbHandler.RCB_INTG_PD

                    result = call_gil_safe(iec61850, "IedConnection_setRCBValues", conn, rcb, changes, True)
                    set_error = UrcbHandler._extract_error(result)
                    if set_error != iec61850.IED_ERROR_OK:
                        last_error = set_error
                        log.debug(f"设置 URCB 值失败，尝试下一个引用: ref={rcb_ref}, nref={nref}, error={set_error}")
                        continue

                    if nref != UrcbHandler._normalize_ref(rcb_ref):
                        log.info(f"URCB 使用基础引用设置成功: ref={rcb_ref}, nref={nref}")
                    log.info(f"URCB RptEna 已{'使能' if enable else '禁用'}: {rcb_ref}")
                    return True
                finally:
                    with contextlib.suppress(Exception):
                        iec61850.ClientReportControlBlock_destroy(rcb)

            log.warning(f"设置 URCB RptEna 失败: ref={rcb_ref}, error={last_error}")
            return False
        except Exception as e:
            log.error(f"设置 URCB RptEna 异常: {rcb_ref}, {e}")
            return False

    @staticmethod
    def disable_direct(connection, rcb_ref: str) -> bool:
        """Disable URCB by writing only RptEna=False."""
        if not HAS_IEC61850:
            return False
        conn = connection.connection
        if not conn:
            log.warning(f"URCB 禁用失败: 连接不可用, ref={rcb_ref}")
            return False

        last_error = None
        try:
            for nref in UrcbHandler._candidate_refs(rcb_ref):
                rcb = UrcbHandler._create_rcb_block(nref)
                if not rcb:
                    continue

                try:
                    iec61850.ClientReportControlBlock_setRptEna(rcb, False)
                    result = call_gil_safe(
                        iec61850, "IedConnection_setRCBValues", conn, rcb, UrcbHandler.RCB_RPT_ENA, True
                    )
                    set_error = UrcbHandler._extract_error(result)
                    if set_error != iec61850.IED_ERROR_OK:
                        last_error = set_error
                        log.debug(f"URCB 禁用失败，尝试下一个引用: ref={rcb_ref}, nref={nref}, error={set_error}")
                        continue

                    if nref != UrcbHandler._normalize_ref(rcb_ref):
                        log.info(f"URCB 使用基础引用禁用成功: ref={rcb_ref}, nref={nref}")
                    log.info(f"URCB 已禁用: {rcb_ref}")
                    return True
                finally:
                    with contextlib.suppress(Exception):
                        iec61850.ClientReportControlBlock_destroy(rcb)

            log.warning(f"URCB 禁用失败: ref={rcb_ref}, error={last_error}")
            return False
        except Exception as e:
            log.error(f"URCB 禁用异常: {rcb_ref}, {e}")
            return False

    @staticmethod
    def trigger_gi(connection, rcb_ref: str) -> bool:
        """Trigger URCB GI."""
        if not HAS_IEC61850:
            return False
        conn = connection.connection
        if not conn:
            return False

        from .callback import ReportCallbackHandler

        ReportCallbackHandler.mark_pending_gi(rcb_ref)
        log.info(f"URCB trigger_gi 开始: rcb_ref={rcb_ref}")

        if UrcbHandler._trigger_gi_write_object(conn, rcb_ref):
            return True

        log.warning(f"URCB GI 直接写属性失败，已跳过 setRCBValues 同步写入以避免进程卡死: {rcb_ref}")
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
                buf_ovfl=bool(opt_val & 0x20),
                entry_id=bool(opt_val & 0x40),
                config_ref=bool(opt_val & 0x80),
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
