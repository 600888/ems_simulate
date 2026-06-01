"""服务端报告管理器 - 在 MMS 模型中注册 ReportControlBlock

在服务端 (IEC61850Server) 的 LLN0 下创建 RCB，
使 EMS 仿真的服务端设备具备报告发布能力。

创建策略:
1. 优先使用 libIEC61850 的 ReportControlBlock_create API
2. 如果 API 未暴露到 Python SWIG，回退到 ICD 模型声明方式
"""

from typing import Any, Dict, List, Optional

from ...defs.constants import HAS_IEC61850
from ...defs.types import OptFields, TrgOps
from ...log import log

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class ReportManager:
    """服务端报告管理器

    在 IedModel 的 LLN0 下创建 ReportControlBlock，
    管理 RCB 生命周期和报告生成。
    """

    def __init__(self, builder, model_name: str = "EMS"):
        """初始化报告管理器

        Args:
            builder: IedModelBuilder 实例 (datamodels/builder.py)
            model_name: IED 模型名称
        """
        self._builder = builder
        self.model_name = model_name
        self._rcb_list: list[dict[str, Any]] = []
        self._model_changed: bool = False

    @property
    def rcb_list(self) -> list[dict[str, Any]]:
        """获取已注册的 RCB 列表"""
        return list(self._rcb_list)

    @property
    def model_changed(self) -> bool:
        return self._model_changed

    @model_changed.setter
    def model_changed(self, value: bool):
        self._model_changed = value

    def register_rcb(
        self,
        ld_inst: str,
        name: str,
        rcb_type: str = "BRCB",
        rpt_id: str = "",
        data_set_ref: str = "",
        conf_rev: int = 1,
        buf_time: int = 0,
        intg_period: int = 0,
        trg_ops: Optional[dict[str, bool]] = None,
        opt_fields: Optional[dict[str, bool]] = None,
    ) -> bool:
        """在 MMS 模型中注册 ReportControlBlock

        在指定 LD 的 LLN0 逻辑节点下创建报告控制块。

        Args:
            ld_inst: 逻辑设备实例名
            name: RCB 名称 (如 "brcb01")
            rcb_type: "BRCB" 或 "URCB"
            rpt_id: 报告标识 (默认使用 name)
            data_set_ref: 绑定的 DataSet 引用
            conf_rev: 配置修订号
            buf_time: 缓冲时间 (ms), 仅 BRCB
            intg_period: 完整性周期 (ms), 仅 URCB
            trg_ops: 触发选项
            opt_fields: 可选字段

        Returns:
            bool 是否成功
        """
        if not self._builder.model:
            log.warning(f"register_rcb [{name}]: 模型未初始化")
            return False

        if not rpt_id:
            rpt_id = name

        lln0_key = f"{ld_inst}/LLN0"
        lln0 = self._builder.ln_map.get(lln0_key)

        if lln0 is None:
            if ld_inst == self._builder.ld_name:
                self._builder.ensure_base_ld()
                lln0 = self._builder.ln_map.get(lln0_key)
            else:
                self._builder.get_or_create_ld(ld_inst)
                lln0 = self._builder.ln_map.get(lln0_key)
                log.info(f"为 register_rcb 自动创建 LD/LLN0: {ld_inst}")

        if not lln0:
            log.warning(f"无法注册 RCB: LLN0 未找到 (ld_inst={ld_inst})")
            return False

        buffered = rcb_type == "BRCB"

        # 尝试使用 ReportControlBlock_create API
        success = self._try_api_create(
            name, lln0, rpt_id, data_set_ref, conf_rev, buffered, buf_time, intg_period, trg_ops, opt_fields
        )
        if success:
            log.info(f"RCB 通过 API 创建成功: {name}, ld={ld_inst}, type={rcb_type}")
        else:
            # 如果 API 不可用, 记录到模型目录 (由 ICD 导出时生成)
            log.info(f"RCB 记录到目录 (API 不可用): {name}, ld={ld_inst}, type={rcb_type}")

        # 记录 RCB 信息
        rcb_info = {
            "ld_inst": ld_inst,
            "name": name,
            "rcb_type": rcb_type,
            "rpt_id": rpt_id,
            "data_set_ref": data_set_ref,
            "conf_rev": conf_rev,
            "buf_time": buf_time,
            "intg_period": intg_period,
            "rpt_ena": False,
            "sq_num": 0,
            "purge_buf": False,
            "entry_id": None,
            "time_of_entry": None,
            "owner": "",
            "resv": False,
            "trg_ops": trg_ops or {"dchg": True, "qchg": False, "dupd": False, "period": False, "gi": True},
            "opt_fields": opt_fields
            or {
                "seq_num": True,
                "time_stamp": True,
                "data_set": True,
                "reason_code": True,
                "data_ref": False,
                "entry_id": True,
                "config_ref": False,
                "buf_ovfl": False,
            },
        }
        self._rcb_list.append(rcb_info)
        self._model_changed = True
        return True

    def _try_api_create(
        self,
        name: str,
        lln0,
        rpt_id: str,
        data_set_ref: str,
        conf_rev: int,
        buffered: bool,
        buf_time: int,
        intg_period: int,
        trg_ops: Optional[dict[str, bool]] = None,
        opt_fields: Optional[dict[str, bool]] = None,
    ) -> bool:
        """尝试使用 ReportControlBlock_create API 创建 RCB

        libIEC61850 的部分版本在 Python SWIG 绑定中可能未暴露此 API。

        注意: ReportControlBlock_create 的真实签名为
        (name, parent, rptId, isBuffered, dataSetName, confRef, trgOps, options, bufTm, intgPd)。
        dataSetName 期望 "LNName$dataSetName" 形式 (parent 已是 LN, 不含 LD 前缀)。
        """
        if not HAS_IEC61850:
            return False

        try:
            # 检查 API 是否可用
            if not hasattr(iec61850, "ReportControlBlock_create"):
                log.debug("ReportControlBlock_create API 不可用")
                return False

            # data_set_ref: "LD/LN$ds" -> dataSetName: "LN$ds"
            ds_name = data_set_ref.split("/", 1)[-1] if "/" in data_set_ref else data_set_ref

            t = trg_ops or {}
            trg_val = (
                (0x01 if t.get("dchg") else 0)
                | (0x02 if t.get("qchg") else 0)
                | (0x04 if t.get("dupd") else 0)
                | (0x08 if t.get("period") else 0)
                | (0x10 if t.get("gi") else 0)
            ) or (0x01 | 0x10)
            o = opt_fields or {}
            opt_val = (
                (0x01 if o.get("seq_num") else 0)
                | (0x02 if o.get("time_stamp") else 0)
                | (0x04 if o.get("reason_code") else 0)
                | (0x08 if o.get("data_set") else 0)
                | (0x10 if o.get("data_ref") else 0)
                | (0x40 if o.get("entry_id") else 0)
                | (0x80 if o.get("config_ref") else 0)
            ) or (0x01 | 0x02 | 0x08)

            rcb = iec61850.ReportControlBlock_create(
                name,
                lln0,
                rpt_id,
                buffered,
                ds_name,
                conf_rev,
                trg_val,
                opt_val,
                buf_time,
                intg_period,
            )
            if rcb:
                # 保持引用防止 GC
                if hasattr(self._builder, "keep_alive"):
                    self._builder.keep_alive.append(rcb)
                log.info(f"ReportControlBlock_create 成功: {name}, dataSet={ds_name}")
                return True
            else:
                log.warning(f"ReportControlBlock_create 返回 None: {name}, dataSet={ds_name}")
                return False
        except Exception as e:
            log.debug(f"ReportControlBlock_create 不可用 (非致命): {e}")
            return False

    def browse_rcbs(self) -> list[dict[str, Any]]:
        """返回服务器上所有已注册的 RCB 目录"""
        return list(self._rcb_list)

    def add_to_pending(self, rcb_config: dict[str, Any]) -> None:
        """添加 RCB 配置到待注册队列（启动后批量注册）

        Args:
            rcb_config: RCB 配置字典
        """
        self._rcb_list.append(rcb_config)
        self._model_changed = True

    def apply_pending_rcbs(self) -> int:
        """批量处理待注册的 RCB 配置

        在模型构建完成后调用。

        Returns:
            成功注册数
        """
        applied = 0
        for rcb in self._rcb_list:
            try:
                # 跳过已通过 API 创建的 RCB (检查是否已有 rpt_id 标记)
                if rcb.get("_applied", False):
                    applied += 1
                    continue

                success = self.register_rcb(
                    ld_inst=rcb.get("ld_inst", ""),
                    name=rcb.get("name", ""),
                    rcb_type=rcb.get("rcb_type", "BRCB"),
                    rpt_id=rcb.get("rpt_id", ""),
                    data_set_ref=rcb.get("data_set_ref", ""),
                    conf_rev=rcb.get("conf_rev", 1),
                    buf_time=rcb.get("buf_time", 0),
                    intg_period=rcb.get("intg_period", 0),
                )
                if success:
                    rcb["_applied"] = True
                    applied += 1
            except Exception as e:
                log.warning(f"应用 RCB 配置失败: {rcb.get('name', '')}, {e}")

        if applied > 0:
            log.info(f"已应用 {applied} 个 RCB 配置")
        return applied
