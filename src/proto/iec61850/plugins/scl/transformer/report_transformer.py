"""SclReportTransformer — SclDocument → Report 配置数据

替代 IcdGooseImporter.get_report_controls() 的逻辑:
  SclDocument → ReportControl 配置列表
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..model.enums import FC_TO_IEC_TYPE
from ..model.scl_document import (
    SclDataSet,
    SclDocument,
    SclLDevice,
    SclLN,
    SclReportControl,
)


@dataclass
class ReportControlInfo:
    """ReportControl 转换结果"""

    ld_inst: str = ""
    name: str = ""
    rcb_type: str = ""  # "BRCB" / "URCB"
    rpt_id: str = ""
    dat_set: str = ""
    data_set_ref: str = ""
    conf_rev: int = 1
    buf_time: int = 0
    intg_period: int = 0
    ln_name: str = ""
    trg_ops: dict[str, bool] = field(default_factory=dict)
    opt_fields: dict[str, bool] = field(default_factory=dict)
    entries: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ReportTransformResult:
    """Report 转换结果"""

    report_controls: list[ReportControlInfo] = field(default_factory=list)


class SclReportTransformer:
    """SCL Report 转换器"""

    def __init__(self, doc: SclDocument):
        self._doc = doc

    def transform(self) -> ReportTransformResult:
        """执行转换"""
        result = ReportTransformResult()

        for ied in self._doc.ieds:
            for ap in ied.access_points:
                if not ap.server:
                    continue
                for ld in ap.server.ldevices:
                    all_lns = ([ld.ln0] + ld.lns) if ld.ln0 else ld.lns
                    for ln in all_lns:
                        self._transform_ln(ln, ld, result)

        return result

    def _transform_ln(
        self,
        ln: SclLN,
        ld: SclLDevice,
        result: ReportTransformResult,
    ) -> None:
        """转换单个 LN 的 ReportControl"""
        ds_map: dict[str, SclDataSet] = {ds.name: ds for ds in ln.datasets}

        for rc in ln.report_controls:
            info = self._build_report_info(rc, ln, ld, ds_map)
            result.report_controls.append(info)

    def _build_report_info(
        self,
        rc: SclReportControl,
        ln: SclLN,
        ld: SclLDevice,
        ds_map: dict[str, SclDataSet],
    ) -> ReportControlInfo:
        """构建 ReportControlInfo"""
        rcb_type = "BRCB" if rc.buffered else "URCB"
        data_set_ref = f"{ld.inst}/{ln.ln_name}${rc.dat_set}" if rc.dat_set else ""

        # 解析 DataSet 条目
        entries = []
        if rc.dat_set and rc.dat_set in ds_map:
            ds = ds_map[rc.dat_set]
            for fcda in ds.members:
                iec_type = FC_TO_IEC_TYPE.get(fcda.fc, "boolean")
                default_val = _default_value_for_type(iec_type)
                entries.append(
                    {
                        "name": fcda.fcda_ref,
                        "value": default_val,
                        "iec_type": iec_type,
                        "fc": fcda.fc,
                    }
                )

        return ReportControlInfo(
            ld_inst=ld.inst,
            name=rc.name,
            rcb_type=rcb_type,
            rpt_id=rc.rpt_id,
            dat_set=rc.dat_set,
            data_set_ref=data_set_ref,
            conf_rev=rc.conf_rev,
            buf_time=rc.buf_time,
            intg_period=rc.intg_period,
            ln_name=ln.ln_name,
            trg_ops={
                "dchg": rc.trg_ops.dchg,
                "qchg": rc.trg_ops.qchg,
                "dupd": rc.trg_ops.dupd,
                "period": rc.trg_ops.period,
                "gi": rc.trg_ops.gi,
            },
            opt_fields={
                "seq_num": rc.opt_fields.seq_num,
                "time_stamp": rc.opt_fields.time_stamp,
                "data_set": rc.opt_fields.data_set,
                "reason_code": rc.opt_fields.reason_code,
                "data_ref": rc.opt_fields.data_ref,
                "entry_id": rc.opt_fields.entry_id,
                "config_ref": rc.opt_fields.config_ref,
                "buf_ovfl": rc.opt_fields.buf_ovfl,
            },
            entries=entries,
        )


def _default_value_for_type(iec_type: str) -> Any:
    defaults = {
        "boolean": False,
        "integer": 0,
        "float": 0.0,
        "string": "",
        "bitstring": 0,
        "timestamp": 0,
    }
    return defaults.get(iec_type, False)
