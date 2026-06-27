"""服务端报告管理器 - 在 MMS 模型中注册 ReportControlBlock

在服务端 (IEC61850Server) 的 LLN0 下创建 RCB，
使 EMS 仿真的服务端设备具备报告发布能力。

创建策略:
1. 优先使用 libIEC61850 的 ReportControlBlock_create API
2. 如果 API 未暴露到 Python SWIG，回退到 ICD 模型声明方式
"""

from typing import Any

from ...defs.constants import HAS_IEC61850
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
        # IedServer 运行时引用（start() 后注入）
        self._ied_server = None
        # 保存每个 RCB 的 RptEna DataAttribute 引用，用于读取运行时状态
        self._rptena_da_map: dict[str, Any] = {}

    @property
    def rcb_list(self) -> list[dict[str, Any]]:
        """获取已注册的 RCB 列表"""
        return list(self._rcb_list)

    def set_server(self, server) -> None:
        """注入 IedServer 引用

        用于直接通过模型 DataAttribute 读取 RCB 运行时状态（如 RptEna），
        不需要额外的 MMS 连接。

        Args:
            server: IedServer 对象 (start() 后可用)
        """
        self._ied_server = server
        log.info("ReportManager 已注入 IedServer 引用")

    def browse_rcbs(self) -> list[dict[str, Any]]:
        """返回服务器上所有已注册的 RCB 目录（运行时状态从 IedServer 直接读取）"""
        if not self._ied_server or not hasattr(iec61850, "IedServer_getBooleanAttributeValue"):
            return list(self._rcb_list)

        results = []
        for rcb_info in self._rcb_list:
            name = rcb_info.get("name", "")
            synced = dict(rcb_info)

            rpt_ena_da = self._rptena_da_map.get(name)
            if rpt_ena_da is not None and hasattr(rpt_ena_da, "this"):
                try:
                    runtime_rpt_ena = iec61850.IedServer_getBooleanAttributeValue(self._ied_server, rpt_ena_da)
                    if runtime_rpt_ena is not None:
                        synced["rpt_ena"] = bool(runtime_rpt_ena)
                except Exception as e:
                    log.debug(f"读取 RCB [{name}] RptEna 运行时状态失败: {e}")

            results.append(synced)
        return results

    def _register_rptena_da(self, rc_name: str, da) -> None:
        """保存 RptEna DataAttribute 引用

        Args:
            rc_name: RCB 名称
            da: RptEna 的 DataAttribute 对象
        """
        if da is not None and hasattr(da, "this"):
            self._rptena_da_map[rc_name] = da

    def _get_rcb_rptena_da(self, rcb_obj) -> Any:
        """从 ReportControlBlock 对象获取 RptEna 的 DataAttribute"""
        try:
            return iec61850.ReportControlBlock_getRptEna(rcb_obj)
        except Exception as e:
            log.error(f"_get_rcb_rptena_da 失败: {e}")
        return None

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
        trg_ops: dict[str, bool] | None = None,
        opt_fields: dict[str, bool] | None = None,
        ln_name: str = "LLN0",
    ) -> bool:
        """在 MMS 模型中注册 ReportControlBlock

        在指定 LD 的指定 LN（通常为 LLN0）下创建报告控制块。

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
            ln_name: RCB 所属逻辑节点名 (默认 "LLN0")，取自 ICD 文件的 LN 名称

        Returns:
            bool 是否成功
        """
        if not self._builder.model:
            log.warning(f"register_rcb [{name}]: 模型未初始化")
            return False

        if not rpt_id:
            rpt_id = name

        ln_key = f"{ld_inst}/{ln_name}"
        ln_node = self._builder.ln_map.get(ln_key)

        if ln_node is None:
            ln_node = self._builder.get_or_create_ln(ld_inst, ln_name)
            log.info(f"为 register_rcb 自动创建 LN: {ln_key}")

        if not ln_node:
            log.warning(f"无法注册 RCB: LN 未找到 (ld_inst={ld_inst}, ln_name={ln_name})")
            return False

        buffered = rcb_type == "BRCB"

        # 尝试使用 ReportControlBlock_create API
        api_success, api_reason = self._try_api_create(
            name, ln_node, rpt_id, data_set_ref, conf_rev, buffered, buf_time, intg_period, trg_ops, opt_fields
        )
        if api_success:
            log.info(f"RCB 通过 API 创建成功: {name}, ld={ld_inst}, ln={ln_name}, type={rcb_type}")
        else:
            # API 不可用或失败，RCB 仅记录到 Python 目录未写入 MMS 模型
            log.warning(
                f"RCB 未能创建到 MMS 模型: {name}, ld={ld_inst}, ln={ln_name}, type={rcb_type}, 原因: {api_reason}"
            )

        # 记录 RCB 信息
        rcb_info = {
            "ld_inst": ld_inst,
            "ln_name": ln_name,
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
            "time_of_entry": "",
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
        return api_success

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
        trg_ops: dict[str, bool] | None = None,
        opt_fields: dict[str, bool] | None = None,
    ) -> tuple[bool, str]:
        """尝试使用 ReportControlBlock_create API 创建 RCB

        libIEC61850 的部分版本在 Python SWIG 绑定中可能未暴露此 API。

        注意: ReportControlBlock_create 的真实签名为
        (name, parent, rptId, isBuffered, dataSetName, confRef, trgOps, options, bufTm, intgPd)。
        dataSetName 期望 DataSet 本地名称，parent 已是 LN。

        Returns:
            (success: bool, reason: str) - 成功/失败标志及原因描述
        """
        if not HAS_IEC61850:
            return False, "pyiec61850 未安装"

        try:
            # data_set_ref: "LD/LN$ds" -> dataSetName: "ds"
            ds_name = data_set_ref.rsplit("/", 1)[-1].rsplit("$", 1)[-1].rsplit(".", 1)[-1] if data_set_ref else ""

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
                # 获取 RptEna DataAttribute，用于后续读取运行时状态
                rpt_ena_da = self._get_rcb_rptena_da(rcb)
                if rpt_ena_da is not None:
                    self._register_rptena_da(name, rpt_ena_da)
                    log.debug(f"RCB [{name}] RptEna DataAttribute 已获取")
                else:
                    log.debug(f"RCB [{name}] 无法获取 RptEna DataAttribute (非致命)")
                log.info(f"ReportControlBlock_create 成功: {name}, dataSet={ds_name}")
                return True, ""
            else:
                reason = f"ReportControlBlock_create 返回 None (name={name}, dataSet={ds_name})"
                log.warning(reason)
                return False, reason
        except Exception as e:
            reason = f"ReportControlBlock_create 异常: {type(e).__name__}: {e}"
            log.warning(reason)
            return False, reason

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
                    ln_name=rcb.get("ln_name", "LLN0"),
                    trg_ops=rcb.get("trg_ops"),
                    opt_fields=rcb.get("opt_fields"),
                )
                if success:
                    rcb["_applied"] = True
                    applied += 1
            except Exception as e:
                log.warning(f"应用 RCB 配置失败: {rcb.get('name', '')}, {e}")

        if applied > 0:
            log.info(f"已应用 {applied} 个 RCB 配置")
        return applied
