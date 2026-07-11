"""
IEC 61850 MMS 服务端封装 (门面模式)

组合 IedModelBuilder 和 ServerDataSetManager，
提供统一的服务端 API。保持与原有 IEC61850Server 接口完全向后兼容。
"""

import contextlib
from typing import Any

from .defs import (
    HAS_IEC61850,
)
from .log import log
from .plugins.datamodels.builder import IedModelBuilder
from .plugins.datasets.server import ServerDataSetManager
from .plugins.reports.manager import ReportManager

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850


class IEC61850Server:
    """IEC 61850 MMS 服务端 (门面模式)

    组合 IedModelBuilder 和 ServerDataSetManager，
    提供统一的服务端 API。保持与原有接口完全向后兼容。
    """

    def __init__(
        self,
        ip: str = "0.0.0.0",
        port: int = 102,
        model_name: str = "EMS",
        ied_name: str = "EMSDevice",
        ld_name: str = "GenericLD",
    ):
        if not HAS_IEC61850:
            raise RuntimeError("pyiec61850 未安装，无法创建 IEC 61850 服务器")

        self.ip = ip
        self.port = port
        self.model_name = model_name
        self.ied_name = ied_name
        self.ld_name = ld_name

        # ===== 组合核心组件 =====
        self._builder = IedModelBuilder(model_name, ied_name, ld_name)
        self.model_name = self._builder.model_name  # 同步
        self._ds_manager = ServerDataSetManager(self._builder, self.model_name)
        self._report_manager = ReportManager(self._builder, self.model_name)

        self._server = None
        self._is_running = False
        # dU 描述存储: {do_key: desc}，set_du_descriptions 存储，start() 时自动应用
        self._du_descriptions: dict[str, str] = {}
        # 整改 v2.0: 模型加载状态
        self._model_loaded = False
        self._loaded_icd_path: str = ""
        self._last_import_result = None

    # ===== 向后兼容属性: 委托给 builder =====

    @property
    def _model(self):
        return self._builder.model

    @property
    def _ld(self):
        return self._builder._ld

    @_ld.setter
    def _ld(self, value):
        self._builder._ld = value

    @property
    def _lln0(self):
        return self._builder._lln0

    @_lln0.setter
    def _lln0(self, value):
        self._builder._lln0 = value

    @property
    def _mmxu(self):
        return self._builder._mmxu

    @property
    def _ggio1(self):
        return self._builder._ggio1

    @property
    def _ggio2(self):
        return self._builder._ggio2

    @property
    def _ld_map(self) -> dict[str, Any]:
        return self._builder.ld_map

    @property
    def _ln_map(self) -> dict[str, Any]:
        return self._builder.ln_map

    @property
    def _do_map(self) -> dict[str, Any]:
        return self._builder._do_map

    @property
    def _da_map(self) -> dict[str, Any]:
        return self._builder._da_map

    @property
    def _point_refs(self) -> dict[str, str]:
        return self._builder.point_refs

    @property
    def _point_attrs(self) -> dict[str, Any]:
        return self._builder.point_attrs

    @property
    def _point_fc(self) -> dict[str, str]:
        return self._builder.point_fc

    @property
    def _point_iec_type(self) -> dict[str, str]:
        return self._builder.point_iec_type

    @property
    def _point_mms_type(self) -> dict[str, str]:
        return self._builder.point_mms_type

    @property
    def _standard_bda_list(self) -> list[tuple]:
        return self._builder.standard_bda_list

    @property
    def _keep_alive(self) -> list[Any]:
        return self._builder.keep_alive

    # ===== 向后兼容属性: 委托给 ds_manager =====

    @property
    def _goose_interface(self) -> str:
        return self._ds_manager.goose_interface

    @_goose_interface.setter
    def _goose_interface(self, value):
        self._ds_manager.goose_interface = value

    @property
    def _goose_publishing_enabled(self) -> bool:
        return self._ds_manager.goose_publishing_enabled

    @property
    def _goose_cb_list(self) -> list[dict[str, Any]]:
        return self._ds_manager.goose_cb_list

    @property
    def _dataset_catalog(self) -> list[dict[str, Any]]:
        return self._ds_manager.dataset_catalog

    @property
    def _model_changed(self) -> bool:
        return self._ds_manager.model_changed

    @_model_changed.setter
    def _model_changed(self, value):
        self._ds_manager.model_changed = value

    @property
    def _pending_goose_registrations(self) -> list[dict[str, Any]]:
        return self._ds_manager.pending_registrations

    # ===== 模型构建 (委托给 IedModelBuilder) =====

    def _build_base_model(self):
        """构建基础 IED 模型 (已在 builder __init__ 中完成)"""
        pass  # builder.__init__ 已创建 IedModel

    def _ensure_base_ld(self):
        """懒创建默认 LD (委托给 builder)"""
        self._builder.ensure_base_ld()

    def _get_or_create_ld(self, ld_inst: str):
        """获取或创建逻辑设备 (委托给 builder)"""
        return self._builder.get_or_create_ld(ld_inst)

    def _get_or_create_ln(self, ld_inst: str, ln_name: str):
        """获取或创建逻辑节点 (委托给 builder)"""
        return self._builder.get_or_create_ln(ld_inst, ln_name)

    def add_point(
        self,
        address,
        frame_type: int = 0,
        fc: str = "",
        dchg: bool = False,
        qchg: bool = False,
        dupd: bool = False,
    ) -> str | None:
        """添加测点到数据模型 (委托给 builder)"""
        return self._builder.add_point(address, frame_type, fc, dchg=dchg, qchg=qchg, dupd=dupd)

    def _add_point_simple(self, address, frame_type: int) -> str | None:
        """简单地址模式添加测点 (委托给 builder)"""
        return self._builder._add_point_simple(address, frame_type)

    def _add_point_from_ref(
        self,
        address: str,
        frame_type: int,
        fc: str = "",
        *,
        dchg: bool = False,
        qchg: bool = False,
        dupd: bool = False,
    ) -> str | None:
        """完整引用路径模式添加测点 (委托给 builder)"""
        return self._builder._add_point_from_ref(
            address,
            frame_type,
            fc,
            dchg=dchg,
            qchg=qchg,
            dupd=dupd,
        )

    # ===== FC/IEC type 推断 (委托给 builder) =====

    @staticmethod
    def _infer_fc(frame_type: int, top_da: str) -> str:
        return IedModelBuilder._infer_fc(frame_type, top_da)

    @staticmethod
    def _resolve_fc_const(fc: str):
        return IedModelBuilder._resolve_fc_const(fc)

    @staticmethod
    def _infer_iec_type(frame_type: int, da_parts: list) -> int:
        return IedModelBuilder._infer_iec_type(frame_type, da_parts)

    @staticmethod
    def _infer_iec_type_str(da_parts: list) -> str:
        return IedModelBuilder._infer_iec_type_str(da_parts)

    @staticmethod
    def _infer_iec_type_from_str(iec_type: str, da_parts: list) -> int:
        return IedModelBuilder._infer_iec_type_from_str(iec_type, da_parts)

    def _add_standard_das(self, do_obj, do_key: str, fc: str, frame_type: int, da_parts: list) -> None:
        """为 DO 补充标准 DA (委托给 builder)"""
        self._builder._add_standard_das(do_obj, do_key, fc, frame_type, da_parts)

    def _ensure_fcda_model_nodes(self, ld_inst: str, ln_name: str, do_da_path: str, fc: str, iec_type: str) -> None:
        """确保 FCDA 模型节点 (委托给 builder)"""
        self._builder.ensure_fcda_model_nodes(ld_inst, ln_name, do_da_path, fc, iec_type)

    # ===== DA 解析 (委托给 builder) =====

    def _resolve_da(self, address: str):
        """根据地址解析 DataAttribute (委托给 builder)"""
        return self._builder.resolve_da(address)

    # ===== 服务器生命周期 =====

    def _init_standard_bda_defaults(self):
        """初始化标准 DA 的默认值"""
        if not self._server or not self._is_running:
            return
        import time as time_module

        now_ms = int(time_module.time() * 1000)
        for da, name, iec_type in self._builder.standard_bda_list:
            try:
                if iec_type == "quality":
                    iec61850.IedServer_updateQuality(self._server, da, 0)
                elif iec_type == "timestamp":
                    iec61850.IedServer_updateUTCTimeAttributeValue(self._server, da, now_ms)
                elif iec_type == "string":
                    iec61850.IedServer_updateVisibleStringAttributeValue(self._server, da, "")
            except Exception as e:
                log.warning(f"初始化标准 DA 默认值失败: {name}({iec_type}), error={e}")

    def _apply_pending_registrations(self):
        """处理待注册的 GoCB/DataSet 队列 (委托给 ds_manager)"""
        self._ds_manager.apply_pending_registrations(self.add_goose_control_block, self.register_dataset)

    def reset_model(self):
        """重置数据模型，清除所有已注册的 LD/LN/DO/DA

        用于 ICD 导入场景：清理之前 start() 创建的默认 GenericLD，
        确保模型只包含 ICD 文件中的自定义 LD。
        导入 ICD 后必须重新注册所有 DataSet 和 RCB 才能生效。

        注意：此操作会丢失所有已注册的测点（add_point 添加的），
        调用前应确保测点已在 ICD 导入流程中重新注册。
        """
        self._builder = IedModelBuilder(self.model_name, self.ied_name, self.ld_name)
        self._ds_manager = ServerDataSetManager(self._builder, self.model_name)
        self._report_manager = ReportManager(self._builder, self.model_name)
        self._model_changed = True
        self._model_loaded = False
        self._loaded_icd_path = ""
        self._last_import_result = None
        log.info("数据模型已重置，默认 GenericLD 已清除")

    # ===== 整改 v2.0: 模型加载与设备启动分离 =====

    def load_model(self, icd_path: str, scl_result: Any = None) -> bool:
        """从 ICD 文件加载模型（不启动 MMS 服务）

        将 ICD 文件解析并构建完整 IedModel，
        注册 GOOSE/DataSet/RCB 配置，
        但不创建 IedServer 实例（不占用端口）。

        Args:
            icd_path: ICD 文件路径
            scl_result: 可选，预先解析的 SclImportResult。提供时跳过内部解析步骤。

        Returns:
            是否加载成功
        """
        from .plugins.scl.service.import_service import SclImportService

        log.info(f"正在从 ICD 文件加载模型: {icd_path}")

        # 1. 解析 ICD 文件（复用外部传入的结果，避免重复解析）
        if scl_result is not None:
            result = scl_result
        else:
            service = SclImportService()
            result = service.import_file(icd_path)
        if not result.is_valid:
            log.error(f"ICD 文件校验失败: {icd_path}, 错误数: {result.validation.error_count}")
            return False

        # 2. 重置现有模型
        self.reset_model()

        # 3. 从解析结果构建模型节点
        ied_name = result.ied_name or self.ied_name
        self.ied_name = ied_name
        self.model_name = ied_name

        # 为每个逻辑设备创建 LD
        seen_lds: set[str] = set()
        for point in (
            result.points.yc_points + result.points.yx_points + result.points.yk_points + result.points.yt_points
        ):
            address = point.reg_addr
            if "/" not in address:
                continue
            ld_inst = address.split("/")[0]
            if ld_inst not in seen_lds:
                seen_lds.add(ld_inst)
                self._get_or_create_ld(ld_inst)
                log.debug(f"创建逻辑设备: {ld_inst}")

            # 解析 LN/DO/DA
            rest = address[address.index("/") + 1 :]
            if "." not in rest:
                continue
            ln_name = rest[: rest.index(".")]
            self._get_or_create_ln(ld_inst, ln_name)

        # 将 ICD 中的测点注册到数据模型（DO/DA 节点）
        registered_count = 0

        def _register_point(point, frame_type: int, default_fc: str) -> bool:
            return bool(
                self._builder._add_point_from_ref(
                    point.reg_addr,
                    frame_type,
                    getattr(point, "fc", "") or default_fc,
                    iec_type_name=getattr(point, "iec_type", ""),
                    mms_type=getattr(point, "mms_type", ""),
                    dchg=bool(getattr(point, "dchg", False)),
                    qchg=bool(getattr(point, "qchg", False)),
                    dupd=bool(getattr(point, "dupd", False)),
                )
            )

        for point in result.points.yc_points:
            if _register_point(point, 0, "MX"):
                registered_count += 1
        for point in result.points.yx_points:
            if _register_point(point, 1, "ST"):
                registered_count += 1
        for point in result.points.yk_points:
            if _register_point(point, 2, "CO"):
                registered_count += 1
        for point in result.points.yt_points:
            if _register_point(point, 3, "CO"):
                registered_count += 1
        log.info(f"已注册 {registered_count} 个测点到数据模型")

        # 4. 注册 DataSet + GOOSE 发布配置
        # 4a. 注册所有 DataSet（必须早于 GoCB，标准顺序：DataSet → GSEControlBlock）
        seen_ds_refs: set[str] = set()

        def _fcda_to_entry(member: dict) -> dict:
            """将 FCDA member dict 转换为 register_dataset 所需的 entry 格式"""
            return {
                "name": member.get("fcda_ref", member.get("name", "")),
                "fc": member.get("fc", "MX"),
            }

        # 纯 DataSet（未被 GOOSE/Report 引用）
        for pd in result.goose.pure_datasets:
            ref = pd.get("ds_ref", "")
            if ref and ref not in seen_ds_refs:
                seen_ds_refs.add(ref)
                entries = pd.get("entries", [])
                self._ds_manager.register_dataset(
                    ld_inst=pd.get("ld_inst", ""),
                    ds_name=pd.get("ds_name", ""),
                    data_set_ref=ref,
                    entries=entries,
                )

        # GOOSE 控制块引用的 DataSet
        for gse in result.goose.gse_controls:
            ref = gse.data_set_ref
            if ref and ref not in seen_ds_refs:
                seen_ds_refs.add(ref)
                entries = [_fcda_to_entry(m) for m in gse.dataset_members]
                ld_inst = gse.ld_inst
                ds_name = ref.split("$")[-1] if "$" in ref else ""
                self._ds_manager.register_dataset(
                    ld_inst=ld_inst,
                    ds_name=ds_name,
                    data_set_ref=ref,
                    entries=entries,
                )

        # Report 引用的 DataSet
        for rc in result.reports.report_controls:
            ref = rc.data_set_ref
            if ref and ref not in seen_ds_refs:
                seen_ds_refs.add(ref)
                entries = [_fcda_to_entry(e) for e in rc.entries]
                ds_name = ref.split("$")[-1] if "$" in ref else rc.dat_set
                self._ds_manager.register_dataset(
                    ld_inst=rc.ld_inst,
                    ds_name=ds_name,
                    data_set_ref=ref,
                    entries=entries,
                )

        # 4b. 注册 GOOSE 控制块（带 _type 标记，确保 apply_pending 能正确处理）
        self._ds_manager.pending_registrations.clear()
        for gse in result.goose.gse_controls:
            pub = gse.to_publisher_dict()
            pub["_type"] = "gocb"
            self._ds_manager.pending_registrations.append(pub)

        # 5. 应用待注册配置
        self._apply_pending_registrations()

        # 6. 应用 Report 配置（去重，RptEnabled max 多实例展开后防止重复）
        seen_rcb_names: set[tuple[str, str, str]] = set()
        for rc in result.reports.report_controls:
            rcb_key = (rc.ld_inst, rc.ln_name or "LLN0", rc.name)
            if rcb_key in seen_rcb_names:
                continue
            seen_rcb_names.add(rcb_key)
            try:
                self._report_manager.register_rcb(
                    ld_inst=rc.ld_inst,
                    name=rc.name,
                    rpt_id=rc.rpt_id,
                    data_set_ref=rc.dat_set,
                    conf_rev=rc.conf_rev,
                    buf_time=rc.buf_time,
                    intg_period=rc.intg_period,
                    rcb_type=rc.rcb_type,
                    ln_name=rc.ln_name,
                    trg_ops=rc.trg_ops,
                    opt_fields=rc.opt_fields,
                )
            except Exception as e:
                log.warning(f"注册 ReportControl 失败: {rc.name}, error={e}")

        self._model_loaded = True
        self._loaded_icd_path = icd_path
        self._last_import_result = result  # 存储解析结果，供后续获取测点列表
        log.info(f"IED 模型加载完成: {ied_name}, LD={len(seen_lds)}, ICD={icd_path}")
        return True

    def get_icd_points(self) -> dict[str, list]:
        """获取最近一次 ICD 导入的测点列表

        Returns:
            {"yc_points": [...], "yx_points": [...], "yk_points": [...], "yt_points": [...]}
            每个 point 包含 code, name, reg_addr, fc, cdc, da_name
        """
        if not self._model_loaded or self._last_import_result is None:
            return {"yc_points": [], "yx_points": [], "yk_points": [], "yt_points": []}
        result = self._last_import_result
        return {
            "yc_points": result.points.yc_points,
            "yx_points": result.points.yx_points,
            "yk_points": result.points.yk_points,
            "yt_points": result.points.yt_points,
        }

    def start_device(self) -> bool:
        """启动 MMS 服务（模型必须已加载）

        先决条件: 必须先调用 load_model() 加载 ICD 模型。

        Returns:
            是否启动成功
        """
        if self._is_running:
            log.warning("MMS 服务器已在运行中")
            return True

        if not self._model_loaded:
            log.error("模型未加载，请先调用 load_model(icd_path)")
            return False

        log.info(f"正在启动 MMS 服务器 (模型: {self.ied_name})...")

        self._server = iec61850.IedServer_create(self._builder.model)
        if not self._server:
            self._is_running = False
            log.error("IedServer_create 失败")
            return False

        iec61850.IedServer_setServerIdentity(self._server, "EMS", self.model_name, "1.0")
        self._is_running = True
        iec61850.IedServer_start(self._server, self.port)

        if iec61850.IedServer_isRunning(self._server):
            log.info(f"IEC 61850 MMS 服务器启动成功 (模型: {self.ied_name}, 端口: {self.port})")
            try:
                self._report_manager.set_server(self._server)
            except Exception as e:
                log.warning(f"注入 ReportManager IedServer 引用失败: {e}")
            try:
                self._init_standard_bda_defaults()
                self._apply_du_descriptions()
            except Exception as e:
                log.warning(f"初始化标准 DA 默认值异常: {e}")
            self._try_enable_goose_publishing()
            import platform
            import time as _time

            _time.sleep(0.3)
            if platform.system() != "Windows":
                try:
                    self._enable_all_goose_cbs()
                except Exception as e:
                    log.warning(f"设置 GoCB GoEna 异常: {e}")
            return True
        else:
            self._is_running = False
            log.error(f"IEC 61850 MMS 服务器启动失败 (端口: {self.port})")
            return False

    @property
    def model_loaded(self) -> bool:
        """模型是否已加载"""
        return self._model_loaded

    @property
    def loaded_icd_path(self) -> str:
        """已加载的 ICD 文件路径"""
        return self._loaded_icd_path

    def apply_model_changes(self) -> bool:
        """应用模型变更: 若 IedServer 已运行且有变更，重建 IedServer"""
        if not self._model_changed or not self._is_running:
            return False
        log.info("检测到 IedModel 变更，重建 IedServer 以更新 MMS 命名空间...")
        self._model_changed = False
        try:
            if self._server:
                try:
                    iec61850.IedServer_stop(self._server)
                    iec61850.IedServer_destroy(self._server)
                except Exception as e:
                    log.warning(f"停止旧 IedServer 时出错: {e}")
                self._server = None
            import time as _time

            _time.sleep(0.5)

            # 重建前重新应用待注册的 RCB (重建 IedServer 后模型会丢失上次创建的 RCB)
            rc_reapplied = 0
            if self._report_manager.model_changed:
                rc_reapplied = self._report_manager.apply_pending_rcbs()
                if rc_reapplied > 0:
                    log.info(f"IedServer 重建前重新创建了 {rc_reapplied} 个 RCB")

            self._server = iec61850.IedServer_create(self._builder.model)
            if not self._server:
                self._is_running = False
                log.error("重建 IedServer 失败")
                return False
            iec61850.IedServer_setServerIdentity(self._server, "EMS", self.model_name, "1.0")
            iec61850.IedServer_start(self._server, self.port)
            if iec61850.IedServer_isRunning(self._server):
                log.info("IedServer 重建成功")
                try:
                    self._report_manager.set_server(self._server)
                except Exception as e:
                    log.warning(f"重建后注入 ReportManager IedServer 引用失败: {e}")
                self._init_standard_bda_defaults()
                self._apply_du_descriptions()
                self._try_enable_goose_publishing()
                import platform
                import time as _time

                _time.sleep(0.3)
                if platform.system() != "Windows":
                    self._enable_all_goose_cbs()
                return True
            else:
                self._is_running = False
                log.error("IedServer 重建后启动失败")
                return False
        except Exception as e:
            log.error(f"重建 IedServer 失败: {e}", exc_info=True)
            self._is_running = False
            return False

    def start(self, register_default_rcbs: bool = True):
        """启动 IEC 61850 MMS 服务器

        v3.0+: 必须先通过 load_model() 加载 ICD 模型才能启动，不再支持默认 GenericLD 模型。

        Args:
            register_default_rcbs: 是否注册默认 BRCB (brcb01/brcb02)。
                ICD 导入时应设为 False，避免在默认 LD 上创建多余 RCB。
        """
        if not self._model_loaded:
            log.error("启动失败: 未加载 ICD 模型，请先调用 load_model(icd_path)")
            return

        if self._is_running:
            if self._model_changed:
                self.apply_model_changes()
            return

        if register_default_rcbs:
            self._register_default_rcbs()
        else:
            log.info("跳过默认 RCB 注册 (register_default_rcbs=False，ICD 已提供 RCB 配置)")
        self._apply_pending_registrations()

        log.info(
            f"IedServer_create 前模型诊断: "
            f"GoCB={len(self._goose_cb_list)}, "
            f"DataSet={len(self._dataset_catalog)}, "
            f"pending={len(self._pending_goose_registrations)}, "
            f"LD={list(self._ld_map.keys()) or [self.ld_name]}, "
            f"LN={list(self._ln_map.keys())}"
        )

        self._server = iec61850.IedServer_create(self._builder.model)
        iec61850.IedServer_setServerIdentity(self._server, "EMS", self.model_name, "1.0")
        self._is_running = True
        iec61850.IedServer_start(self._server, self.port)

        if iec61850.IedServer_isRunning(self._server):
            log.info(f"IEC 61850 MMS 服务器已启动, 端口: {self.port}")
            # 注入 IedServer 引用到 ReportManager，使 UI 能读取 RCB 运行时状态
            try:
                self._report_manager.set_server(self._server)
            except Exception as e:
                log.warning(f"注入 ReportManager IedServer 引用失败 (非致命): {e}")
            try:
                self._init_standard_bda_defaults()
                self._apply_du_descriptions()
            except Exception as e:
                log.warning(f"初始化标准 DA 默认值异常 (非致命): {e}")
            self._try_enable_goose_publishing()
            import platform
            import time as _time

            _time.sleep(0.3)
            if platform.system() != "Windows":
                try:
                    self._enable_all_goose_cbs()
                except Exception as e:
                    log.warning(f"设置 GoCB GoEna 异常 (非致命): {e}")
            else:
                log.info("Windows 平台跳过 GoEna 设置")
        else:
            self._is_running = False
            log.error(f"IEC 61850 服务器启动失败, 端口: {self.port}")

    def _try_enable_goose_publishing(self):
        """尝试启用 GOOSE 以太网发布（非致命）"""
        import platform

        if platform.system() == "Windows":
            log.info("GOOSE 发布: Windows 平台不支持原始套接字，已跳过")
            self._ds_manager._goose_publishing_enabled = False
            return
        interface = self._ds_manager.goose_interface
        if interface and interface != "eth0":
            try:
                import subprocess

                result = subprocess.run(["ip", "link", "show", interface], capture_output=True, timeout=3)
                if result.returncode != 0:
                    log.warning(f"GOOSE 网络接口 '{interface}' 不存在，跳过")
                    self._ds_manager._goose_publishing_enabled = False
                    return
            except Exception:
                pass
        try:
            iec61850.IedServer_setGooseInterfaceId(self._server, interface)
        except Exception as e:
            log.warning(f"设置 GOOSE 网络接口失败 ({interface}): {e}")
        try:
            iec61850.IedServer_enableGoosePublishing(self._server)
            log.info("GOOSE 发布服务已启用")
            self._ds_manager._goose_publishing_enabled = True
        except Exception as e:
            log.warning(f"启用 GOOSE 发布服务失败: {e}")
            self._ds_manager._goose_publishing_enabled = False

    def stop(self):
        """停止 IEC 61850 MMS 服务器"""
        if self._server and self._is_running:
            iec61850.IedServer_stop(self._server)
            iec61850.IedServer_destroy(self._server)
            self._server = None
            self._is_running = False
            log.info("IEC 61850 服务器已停止")

    def restart(self) -> bool:
        """重启 MMS 服务器"""
        if self._server:
            try:
                iec61850.IedServer_stop(self._server)
                iec61850.IedServer_destroy(self._server)
            except Exception:
                pass
        self._server = None
        self._is_running = False
        import time as _time

        _time.sleep(1)
        self._server = iec61850.IedServer_create(self._builder.model)
        if not self._server:
            log.error("重启失败: IedServer_create 返回空")
            return False
        iec61850.IedServer_setServerIdentity(self._server, "EMS", self.model_name, "1.0")
        self._is_running = True
        iec61850.IedServer_start(self._server, self.port)
        if iec61850.IedServer_isRunning(self._server):
            log.info(f"IEC 61850 服务器重启成功, 端口: {self.port}")
            try:
                self._report_manager.set_server(self._server)
            except Exception as e:
                log.warning(f"重启后注入 ReportManager IedServer 引用失败: {e}")
            self._init_standard_bda_defaults()
            self._try_enable_goose_publishing()
            import platform
            import time as _time

            _time.sleep(0.3)
            if platform.system() != "Windows":
                self._enable_all_goose_cbs()
            return True
        else:
            self._is_running = False
            log.error("IEC 61850 服务器重启失败")
            return False

    @property
    def is_running(self) -> bool:
        if self._server:
            return iec61850.IedServer_isRunning(self._server)
        return False

    # ===== 读写 =====

    def get_point_value(self, address, fc: str = "") -> Any:
        """获取测点值"""
        if not self._server or not self._is_running:
            return 0
        addr_str = str(address)
        da, resolved_addr = self._builder.resolve_da(address)
        if not da:
            log.warning(f"IEC61850 读取测点值时未找到 DataAttribute: address={address}")
            return 0
        if not hasattr(da, "this"):
            log.error(f"IEC61850 数据属性对象类型错误: address={address}")
            return 0
        iec_type = self._point_iec_type.get(resolved_addr, self._point_iec_type.get(addr_str, "unknown"))
        try:
            if iec_type == "float":
                value = iec61850.IedServer_getFloatAttributeValue(self._server, da)
                return float(value) if value is not None else 0.0
            elif iec_type == "boolean":
                value = iec61850.IedServer_getBooleanAttributeValue(self._server, da)
                return bool(value) if value is not None else False
            elif iec_type == "integer":
                value = iec61850.IedServer_getInt32AttributeValue(self._server, da)
                return int(value) if value is not None else 0
            elif iec_type == "string":
                value = iec61850.IedServer_getStringAttributeValue(self._server, da)
                return str(value).strip() if value else ""
            elif iec_type == "quality":
                value = iec61850.IedServer_getUInt32AttributeValue(self._server, da)
                return int(value) if value is not None else 0
            elif iec_type == "timestamp":
                value = iec61850.IedServer_getUTCTimeAttributeValue(self._server, da)
                return int(value) if value is not None else 0
            else:
                try:
                    value = iec61850.IedServer_getFloatAttributeValue(self._server, da)
                    return float(value) if value is not None else 0.0
                except Exception:
                    pass
                try:
                    value = iec61850.IedServer_getBooleanAttributeValue(self._server, da)
                    return bool(value) if value is not None else False
                except Exception:
                    pass
                try:
                    value = iec61850.IedServer_getInt32AttributeValue(self._server, da)
                    return int(value) if value is not None else 0
                except Exception:
                    pass
                return 0
        except Exception as e:
            log.error(f"IEC61850 调用底层获取值函数失败: address={address}, error={e}")
            return 0

    def set_point_value(self, address, value: Any, fc: str = "") -> None:
        """设置测点值"""
        if not self._server or not self._is_running:
            return
        addr_str = str(address)
        da, resolved_addr = self._builder.resolve_da(address)
        if not da:
            log.warning(f"IEC61850 设置测点值时未找到 DataAttribute: address={address}")
            return
        if not hasattr(da, "this"):
            log.error(f"IEC61850 数据属性对象类型错误(设置值): address={address}")
            return
        iec_type = self._point_iec_type.get(resolved_addr, self._point_iec_type.get(addr_str, "unknown"))
        try:
            if isinstance(value, str) or iec_type == "string":
                iec61850.IedServer_updateVisibleStringAttributeValue(self._server, da, str(value))
            elif iec_type == "float":
                iec61850.IedServer_updateFloatAttributeValue(self._server, da, float(value))
            elif iec_type == "integer":
                if isinstance(value, int) and not isinstance(value, bool):
                    iec61850.IedServer_updateInt32AttributeValue(self._server, da, int(value))
                else:
                    iec61850.IedServer_updateBooleanAttributeValue(self._server, da, bool(value))
            elif iec_type == "boolean":
                iec61850.IedServer_updateBooleanAttributeValue(self._server, da, bool(value))
            elif iec_type == "quality":
                iec61850.IedServer_updateQuality(self._server, da, int(value))
            elif iec_type == "timestamp":
                iec61850.IedServer_updateUTCTimeAttributeValue(self._server, da, int(value))
            else:
                if isinstance(value, float):
                    iec61850.IedServer_updateFloatAttributeValue(self._server, da, float(value))
                elif isinstance(value, bool):
                    iec61850.IedServer_updateBooleanAttributeValue(self._server, da, bool(value))
                elif isinstance(value, int):
                    iec61850.IedServer_updateInt32AttributeValue(self._server, da, int(value))
        except Exception as e:
            log.error(f"IEC61850 调用底层设置值函数失败: address={address}, value={value}, error={e}")

    # ===== Reports (委托给 report_manager) =====

    @property
    def reports(self):
        """获取 Reports 管理对象"""
        return self._report_manager

    def set_du_descriptions(self, descriptions: dict[str, str]) -> None:
        """存储 DO 的 dU 描述值，服务器运行后自动应用

        Args:
            descriptions: {do_key: desc} 映射,
                          do_key 如 "LD/LLN0.Temp001" (LD_inst/LN_name.DO_name)
        """
        if not descriptions:
            return
        self._du_descriptions.update(descriptions)
        log.info(
            f"已存储 {len(descriptions)} 个 DO 的描述, "
            f"总计 {len(self._du_descriptions)} 个, "
            f"服务器运行={'是' if self._is_running else '否'}"
        )
        self._apply_du_descriptions()

    def _apply_du_descriptions(self) -> None:
        """应用已存储的 dU 描述值到运行中的 IedServer"""
        if not self._du_descriptions or not self._server or not self._is_running:
            log.debug(
                f"_apply_du_descriptions: 条件不满足, desc={len(self._du_descriptions)}, running={self._is_running}"
            )
            return
        set_count = 0
        not_found = []
        for do_key, desc in list(self._du_descriptions.items()):
            if not desc:
                continue
            du_key = f"{do_key}.dU"
            da = self._builder._da_map.get(du_key)
            if da and hasattr(da, "this"):
                try:
                    iec61850.IedServer_updateVisibleStringAttributeValue(self._server, da, str(desc))
                    set_count += 1
                except Exception as e:
                    log.debug(f"设置 dU 描述失败: {do_key}={desc}, {e}")
            else:
                not_found.append(do_key)
        if set_count > 0:
            log.info(f"已应用 {set_count} 个 DO 的 dU 描述值")
        if not_found:
            log.warning(f"以下 {len(not_found)} 个 DO 的 dU DA 未在 _da_map 中找到 (前5): {not_found[:5]}")

    def _build_point_fcda_entries(self) -> list[dict[str, Any]]:
        """从已注册的测点构建 FCDA 条目列表

        DataSet 的 FCDA 条目需要引用 MMS 模型中已存在的 DataAttribute，
        每个条目包含 name(LD/LN.DO.DA)、fc(功能约束) 和 iec_type。

        Returns:
            FCDA 条目列表，每个条目格式:
            {"name": "LD_inst/LN_name.DO_name.mag.f", "fc": "MX", "iec_type": "float"}
        """
        ied_prefix = self.model_name
        entries = []
        for address, ref in self._point_refs.items():
            # ref 格式: "{IEDName}{LD_inst}/{LN_name}.{DO_name}.{DA_path}"
            # FCDA entry name 需要: "{LD_inst}/{LN_name}.{DO_name}.{DA_path}" (不含 IEDName)
            if ref.startswith(ied_prefix):
                fcda_name = ref[len(ied_prefix) :]
            else:
                fcda_name = ref
            fc = self._point_fc.get(address, "MX")
            iec_type = self._point_iec_type.get(address, "unknown")
            mms_type = self._point_mms_type.get(address, "MMS_UNKNOWN")
            entries.append({"name": fcda_name, "fc": fc, "iec_type": iec_type, "mms_type": mms_type})
        return entries

    def _register_default_rcbs(self):
        """注册默认报告控制块 (BRCB/URCB)

        为服务端默认逻辑设备创建 RCB，绑定到对应的 DataSet。
        每个 IED 都应该至少有一个 BRCB 用于支持报告功能。

        注意: 依赖 libIEC61850 的 ReportControlBlock_create API，
        部分版本可能未暴露此 API 到 Python SWIG。
        """
        if not self._builder.model:
            log.debug("_register_default_rcbs: 模型未初始化，跳过")
            return

        # 检查模型中是否已有用户自定义的 LD（来自 ICD 导入等）。
        # 如果已有，说明用户使用了 ICD 自定义模型，跳过默认 GenericLD 的创建。
        default_ld = self.ld_name
        other_lds = [k for k in self._builder.ld_map if k != default_ld]
        if other_lds:
            log.info(f"检测到已有自定义 LD: {other_lds}，跳过默认 RCB 注册")
            return

        # 检查是否已有测点注册到非默认 LD
        has_custom_points = any(not ref.startswith(f"{default_ld}/") for ref in self._builder.point_refs.values())
        if has_custom_points:
            log.info("检测到已有自定义测点，跳过默认 RCB 注册")
            return

        # 为默认 LD 创建 DataSet 和 BRCB
        default_rcbs = [
            {
                "ld_inst": default_ld,
                "ln_name": "LLN0",
                "name": "brcb01",
                "rcb_type": "BRCB",
                "rpt_id": "brcb01",
                "data_set_ref": f"{default_ld}/LLN0$dsReport1",
                "conf_rev": 1,
                "buf_time": 0,
                "trg_ops": {"dchg": True, "qchg": False, "dupd": False, "period": False, "gi": True},
                "opt_fields": {
                    "seq_num": True,
                    "time_stamp": True,
                    "data_set": True,
                    "reason_code": True,
                    "data_ref": False,
                    "entry_id": True,
                    "config_ref": False,
                    "buf_ovfl": False,
                },
            },
            {
                "ld_inst": default_ld,
                "ln_name": "LLN0",
                "name": "brcb02",
                "rcb_type": "BRCB",
                "rpt_id": "brcb02",
                "data_set_ref": f"{default_ld}/LLN0$dsReport2",
                "conf_rev": 1,
                "buf_time": 100,
                "trg_ops": {"dchg": True, "qchg": True, "dupd": False, "period": True, "gi": True},
                "opt_fields": {
                    "seq_num": True,
                    "time_stamp": True,
                    "data_set": True,
                    "reason_code": True,
                    "data_ref": False,
                    "entry_id": True,
                    "config_ref": False,
                    "buf_ovfl": False,
                },
            },
        ]

        # 从已注册的测点构建 FCDA 条目，使 DataSet 有实际数据可报告
        point_entries = self._build_point_fcda_entries()
        if point_entries:
            log.info(f"自动构建 {len(point_entries)} 个 FCDA 条目用于默认报告 DataSet")
        else:
            log.warning(
                "未发现已注册的测点，默认报告 DataSet 将为空！"
                "请确保在调用 start() 前已通过 add_points() 或 add_point() 注册测点。"
            )

        registered_count = 0
        failed_count = 0
        for rcb_cfg in default_rcbs:
            # 先注册 DataSet（如果还不存在）
            ds_name = rcb_cfg["data_set_ref"].split("$")[-1]
            if not any(ds.get("ref") == rcb_cfg["data_set_ref"] for ds in self._ds_manager.browse_datasets()):
                self._ds_manager.register_dataset(
                    ld_inst=rcb_cfg["ld_inst"],
                    ds_name=ds_name,
                    data_set_ref=rcb_cfg["data_set_ref"],
                    entries=point_entries if point_entries else None,
                )
                log.info(f"为默认 RCB 自动创建 DataSet: {rcb_cfg['data_set_ref']}, entries={len(point_entries)}")

            # 注册 RCB
            success = self._report_manager.register_rcb(
                ld_inst=rcb_cfg["ld_inst"],
                name=rcb_cfg["name"],
                rcb_type=rcb_cfg["rcb_type"],
                rpt_id=rcb_cfg["rpt_id"],
                data_set_ref=rcb_cfg["data_set_ref"],
                conf_rev=rcb_cfg["conf_rev"],
                buf_time=rcb_cfg["buf_time"],
                trg_ops=rcb_cfg.get("trg_ops"),
                opt_fields=rcb_cfg.get("opt_fields"),
                ln_name=rcb_cfg.get("ln_name", "LLN0"),
            )
            if success:
                registered_count += 1
                log.info(f"默认 RCB 已注册到 MMS 模型: {rcb_cfg['name']} ({rcb_cfg['rcb_type']})")
            else:
                failed_count += 1
                log.warning(f"默认 RCB 注册失败: {rcb_cfg['name']} ({rcb_cfg['rcb_type']})")

        if failed_count > 0:
            log.warning(
                f"默认 RCB 注册结果: 成功={registered_count}/{len(default_rcbs)}, 失败={failed_count}。"
                f"原因: libIEC61850 的 ReportControlBlock_create API 可能未暴露到 Python SWIG，"
                f"MMS 服务器中将没有报告控制块"
            )

    # ===== 浏览方法 (委托给 builder) =====

    def browse_logical_devices(self) -> list[str]:
        return self._builder.browse_logical_devices()

    def browse_logical_nodes(self, ld_inst: str) -> list[str]:
        return self._builder.browse_logical_nodes(ld_inst)

    def browse_data_objects(self, ld_inst: str, ln_name: str) -> list[dict]:
        return self._builder.browse_data_objects(ld_inst, ln_name)

    def browse_data_attributes(self, ld_inst: str, ln_name: str, do_name: str) -> list[dict]:
        return self._builder.browse_data_attributes(ld_inst, ln_name, do_name)

    # ===== GOOSE / DataSet (委托给 ds_manager) =====

    def add_goose_control_block(
        self,
        name,
        app_id,
        data_set_ref,
        conf_rev,
        go_id="",
        min_time=10,
        max_time=1000,
        ld_inst=None,
        entries=None,
        dst_mac=None,
        vlan_id=0,
        vlan_prio=4,
    ) -> bool:
        """在 LLN0 下创建 GSEControlBlock (委托给 ds_manager)"""
        result = self._ds_manager.add_goose_control_block(
            name,
            app_id,
            data_set_ref,
            conf_rev,
            go_id,
            min_time,
            max_time,
            ld_inst,
            entries,
            dst_mac,
            vlan_id,
            vlan_prio,
        )
        if result and self._server and self._is_running:
            self._model_changed = True
            log.info(f"GoCB {name} 在 IedServer 运行时添加，需要重建 IedServer")
        return result

    def register_dataset(self, ld_inst, ds_name, data_set_ref, entries=None, dataset_catalog=None) -> bool:
        """注册 DataSet (委托给 ds_manager)"""
        result = self._ds_manager.register_dataset(
            ld_inst,
            ds_name,
            data_set_ref,
            entries,
            dataset_catalog,
        )
        if result and self._server and self._is_running:
            self._model_changed = True
            log.info(f"DataSet {ds_name} 在 IedServer 运行时添加，需要重建 IedServer")
        return result

    def _add_fcda_entries_to_dataset(self, data_set, entries, default_ld_inst) -> int:
        """向 DataSet 添加 FCDA 条目 (委托给 ds_manager)"""
        return self._ds_manager._add_fcda_entries_to_dataset(data_set, entries, default_ld_inst)

    def browse_datasets(self) -> list[dict[str, Any]]:
        """浏览已注册的 DataSet (委托给 ds_manager)"""
        return self._ds_manager.browse_datasets()

    def _enable_single_goose_cb(self, ld_inst, cb_name, max_retries=3, retry_delay=0.5):
        """设置单个 GoCB 的 GoEna=TRUE (委托给 ds_manager)"""
        self._ds_manager.enable_single_goose_cb(
            self._server, self.port, self.model_name, ld_inst, cb_name, max_retries, retry_delay
        )

    def _enable_all_goose_cbs(self):
        """设置所有 GoCB 的 GoEna=TRUE (委托给 ds_manager)"""
        self._ds_manager.enable_all_goose_cbs(self._server, self.port, self.model_name)

    def set_goose_interface(self, interface: str):
        """设置 GOOSE 网络接口"""
        self._ds_manager.goose_interface = interface
        if self._server:
            with contextlib.suppress(Exception):
                iec61850.IedServer_setGooseInterfaceId(self._server, interface)

    def destroy(self):
        """销毁服务器和模型"""
        self.stop()
        if self._builder.model:
            iec61850.IedModel_destroy(self._builder.model)
