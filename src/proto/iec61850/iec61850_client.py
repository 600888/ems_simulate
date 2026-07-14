"""
IEC 61850 MMS 客户端封装 (门面模式)

组合 core/ 和 plugins/ 模块，提供统一的客户端 API。
保持与原有 IEC61850Client 接口完全向后兼容。

v3.0 变更: 集成 ModelDiscoveryService，连接时一次发现 → IedModel 缓存 → 多处消费。
"""

from collections.abc import Callable
import contextlib
from typing import Any, cast

from src.proto.iec61850.plugins.datamodels import DataModelsPlugin
from src.proto.iec61850.plugins.datasets import DataSetsPlugin
from src.proto.iec61850.plugins.files import FilesPlugin
from src.proto.iec61850.plugins.model_exporter import ModelExporterPlugin
from src.proto.iec61850.plugins.reports import ReportsPlugin

from .core import (
    Iec61850Connection,
    Iec61850Reader,
    Iec61850Writer,
    PointRegistry,
    get_list_from_linked_list,
    mms_value_to_python,
)
from .core.metadata import MetadataInfo, MetadataReader
from .defs import (
    HAS_IEC61850,
    IecType,
    extract_ln_class,
)
from .defs.mms_types import MmsType
from .log import log
from .model import IedModel
from .model.discovery import DiscoveryProgress, ModelDiscoveryService
from .model.registry_bridge import build_registry_from_model
from .plugins import PluginRegistry, _register_builtin_plugins

if HAS_IEC61850:
    from pyiec61850 import pyiec61850 as iec61850
else:
    iec61850 = None


class IEC61850Client:
    """IEC 61850 MMS 客户端 (门面模式)

    组合 core/ 和 plugins/ 模块，提供统一的客户端 API。
    保持与原有接口完全向后兼容。
    """

    def __init__(
        self,
        ip: str = "127.0.0.1",
        port: int = 102,
        model_name: str = "EMS",
        ld_name: str = "GenericLD",
    ):
        if not HAS_IEC61850:
            raise RuntimeError("pyiec61850 未安装，无法创建 IEC 61850 客户端")

        self.ip = ip
        self.port = port
        self.model_name = model_name
        self.ld_name = ld_name

        # ===== 组合核心组件 =====
        self._conn = Iec61850Connection(ip, port, model_name, ld_name)
        # 报告回调运行在 libIEC61850 的接收线程中。使用独立 association，
        # 避免 DataModel/DataSet 同步读取占用另一条连接时阻塞报告回调。
        self._report_conn = Iec61850Connection(ip, port, model_name, ld_name)
        self._registry = PointRegistry(model_name, ld_name)
        self._reader = Iec61850Reader(self._conn, self._registry)
        self._writer = Iec61850Writer(self._conn, self._registry)

        # ===== 统一模型发现服务 =====
        self._discovery = ModelDiscoveryService()

        # ICD 导入结果缓存
        self._last_import_result = None
        # 所有离线模型都必须等 MMS 连接建立后才能与当前服务端校验。
        # 取值: "cache" / "local" / "import" / None。
        self._offline_model_source: str | None = None
        # ICD 解析出的 RCB 列表（供 UI 展示，不依赖 MMS 连接）
        self._rcbs_from_icd: list[dict[str, Any]] = []

        # ===== 插件系统 =====
        self._plugins = PluginRegistry(auto_register=False)
        _register_builtin_plugins(self._plugins)
        self._plugins.initialize_all(
            self._conn,
            registry=self._registry,
            client=self,
            report_connection=self._report_conn,
        )
        self._reader.set_dataset_reader(self.datasets)

    # ===== 向后兼容属性: 委托给核心组件 =====

    @property
    def _connection(self):
        """底层 IedConnection 对象 (向后兼容)"""
        return self._conn.connection

    @property
    def _is_connected(self) -> bool:
        """连接状态 (向后兼容)"""
        return self._conn.is_connected

    @property
    def _point_refs(self) -> dict[str, str]:
        """地址 -> MMS 引用映射 (向后兼容, 委托给 registry)"""
        return self._registry.point_refs

    @property
    def _point_fc(self) -> dict[str, str]:
        """地址 -> FC 映射 (向后兼容, 委托给 registry)"""
        return self._registry.point_fc

    @property
    def _point_iec_type(self) -> dict[str, str]:
        """地址 -> iec_type 映射 (向后兼容, 委托给 registry)"""
        return self._registry.point_iec_type

    @property
    def _discovered_lds(self) -> list:
        """已发现的 LD 列表 (向后兼容)"""
        return self._conn._discovered_lds

    @property
    def _discovered_goose_items(self) -> list:
        """发现的 GOOSE 控制块 (向后兼容, 委托给 registry)"""
        return self._registry.discovered_goose_items

    @property
    def _discovered_datasets(self) -> list:
        """发现的 DataSet 列表 (向后兼容, 委托给 registry)"""
        return self._registry.discovered_datasets

    @_discovered_datasets.setter
    def _discovered_datasets(self, value):
        self._registry.discovered_datasets = value

    # ===== 连接管理 (委托给 Iec61850Connection) =====

    def connect(self, auto_discover: bool = True) -> bool:
        """连接到 IEC 61850 服务器"""
        connected = self._conn.connect(
            auto_discover=auto_discover,
            discover_callback=self.discover_model if auto_discover else None,
        )
        if connected and not self._ensure_report_connection():
            # 报告通道可按需再次连接；不影响主通道的模型和测点读写。
            log.warning("IEC 61850 主连接成功，但独立报告连接暂未建立")
        return connected

    def disconnect(self):
        """断开连接（仅关闭 MMS 连接，保留模型缓存）

        模型缓存保留在内存和文件缓存中，断开连接不会清除它们。
        如需清除缓存，请调用 clear_cache() 接口。
        """
        if self.datasets:
            self.datasets.invalidate_catalog()
        reports = self.reports
        if reports:
            reports.prepare_disconnect()
        self._report_conn.disconnect()
        self._conn.disconnect()

    def _ensure_report_connection(self) -> bool:
        """确保独立报告 association 可用，并同步主连接的模型前缀信息。"""
        self._report_conn.model_name = self._conn.model_name
        self._report_conn.ld_name = self._conn.ld_name
        self._report_conn._discovered_lds = list(self._conn._discovered_lds)
        if self._report_conn.is_connected:
            return True
        return self._report_conn.connect(auto_discover=False)

    @property
    def is_connected(self) -> bool:
        return self._conn.is_connected

    # ===== 测点管理 (委托给 PointRegistry) =====

    def add_point(self, address, frame_type: int = 0, fc: str = "") -> str:
        """注册测点引用路径 (委托给 PointRegistry)"""
        return self._registry.add_point(address, frame_type, fc)

    # ===== 读写 (委托给 Iec61850Reader/Iec61850Writer) =====

    def read_point(self, address, fc: str = "", mms_type: str = "") -> Any:
        """读取测点值 (委托给 Iec61850Reader)"""
        return self._reader.read(address, fc, mms_type)

    def read_points_batch(
        self,
        addresses: list[str],
        fc_map: dict[str, str] | None = None,
        progress: Callable[[str, int, int, str], None] | None = None,
    ) -> dict[str, Any]:
        """批量读取多个测点值 (委托给 Iec61850Reader)"""
        return self._reader.read_batch(addresses, fc_map, progress)

    def read_metadata(self, address: str, *, fc: str = "") -> MetadataInfo:
        """按需读取测点的品质(q)与时标(t)元数据

        不依赖 PointRegistry，根据 address 解析 DO 引用后直接 MMS 读取。

        Args:
            address: 测点地址 (如 "KG_BAMSCTMP01/MMCL1.Temp001.mag.f")
            fc: 功能约束 (默认 MX)

        Returns:
            MetadataInfo (quality + timestamp)

        Example:
            >>> meta = client.read_metadata("KG_BAMSCTMP01/MMCL1.Temp001.mag.f")
            >>> print(meta.quality.is_valid, meta.timestamp.unix_timestamp_ms)
        """
        from .defs.address import infer_fc_from_address, parse_ref

        parsed = parse_ref(address)
        if not parsed:
            return MetadataInfo()
        ld_inst, ln_name, do_name, _ = parsed
        do_ref = f"{ld_inst}/{ln_name}.{do_name}"
        if not fc:
            fc = self._registry.get_fc(address) or infer_fc_from_address(address)

        reader = MetadataReader()
        return reader.read_metadata(self._conn, do_ref, fc=fc)

    def write_point(self, address, value: Any, fc: str = "") -> bool:
        """写入测点值 (委托给 Iec61850Writer)"""
        return self._writer.write(address, value, fc)

    # ===== 内部方法 (向后兼容, 委托给核心组件) =====

    def _build_ref(self, address) -> str:
        """构建 MMS 引用路径 (委托给 registry)"""
        ref = self._registry.get_ref(address)
        if ref:
            return ref
        return self._registry._build_ref(address)

    def _get_fc_value(self, fc: str):
        """将 FC 字符串转换为 pyiec61850 常量值 (委托给 connection)"""
        return self._conn.get_fc_value(fc)

    def _build_dataset_ref(self, dataset_ref: str) -> str:
        """构建 MMS DataSet 引用 (委托给 connection)"""
        return self._conn.build_dataset_ref(dataset_ref)

    def _mms_value_to_python(self, mms_value, iec_type: str = IecType.UNKNOWN) -> Any:
        """将 MmsValue 转换为 Python 类型 (委托给 core)"""
        return mms_value_to_python(mms_value, iec_type)

    def _get_list_from_linked_list(self, linked_list) -> list[str]:
        """从 LinkedList 提取字符串列表 (委托给 core)"""
        return get_list_from_linked_list(linked_list)

    # ===== 插件属性 (按需暴露) =====

    @property
    def datamodels(self):
        """获取 DataModels 插件"""
        plugins = getattr(self, "_plugins", None)
        if plugins is None:
            return None
        return cast(DataModelsPlugin | None, plugins.get("datamodels"))

    @property
    def datasets(self) -> DataSetsPlugin | None:
        """获取 DataSets 插件"""
        plugins = getattr(self, "_plugins", None)
        if plugins is None:
            return None
        return cast(DataSetsPlugin | None, plugins.get("datasets"))

    @property
    def goose(self):
        """获取 GOOSE 插件"""
        return self._plugins.get("goose")

    @property
    def reports(self):
        """获取 Reports 插件"""
        return cast(ReportsPlugin | None, self._plugins.get("reports"))

    @property
    def files(self) -> FilesPlugin | None:
        """获取 Files 插件 (文件下载服务)"""
        return cast(FilesPlugin | None, self._plugins.get("files"))

    # ===== 文件操作 (委托给 Files 插件) =====

    def list_remote_files(self, directory: str = "") -> list[dict[str, Any]]:
        """浏览远程 IED 文件目录"""
        fp = self.files
        if fp:
            return fp.list_directory(directory)
        return []

    def download_remote_file(self, filename: str, local_path: str = "") -> bytes:
        """从远程 IED 下载文件"""
        fp = self.files
        if fp:
            return fp.get_file(filename, local_path)
        return b""

    # ===== 模型发现 (使用统一 ModelDiscoveryService) =====

    def discover_model(self) -> list[dict[str, Any]]:
        """动态发现并映射服务端的数据模型

        使用 ModelDiscoveryService 统一发现，一次遍历构建 IedModel，
        然后从 IedModel 派生 PointRegistry。
        """
        if not self._conn.is_connected:
            return []

        # 统一发现: 一次遍历，构建并缓存 IedModel
        # 整次在线发现都占用主连接生命周期锁，禁止中途 stop/reconnect
        # 销毁同一个原生 IedConnection。
        operation = self._conn.native_operation()
        guard = operation if hasattr(operation, "__enter__") else contextlib.nullcontext(self._conn.connection)
        with guard as conn:
            if conn is None:
                return []
            model = self._discovery.discover(self._conn)
        report_conn = getattr(self, "_report_conn", None)
        if report_conn is not None:
            report_conn._discovered_lds = list(self._conn._discovered_lds)

        # 从 IedModel 派生 PointRegistry
        discovered = build_registry_from_model(model, self._registry)
        if self.datasets:
            self.datasets.invalidate_catalog()

        # 补充 dU 描述名称 (与 DataModelsPlugin._read_du_description 一致)
        self._fill_du_names(discovered)

        return discovered

    def _fill_du_names(
        self,
        discovered: list[dict[str, Any]],
        progress: DiscoveryProgress | None = None,
    ) -> None:
        """为发现的测点补充 dU 描述名称

        优化: 先构建 do_ref → [point] 索引, 避免 O(N²) 嵌套遍历。
        """
        from .defs.address import parse_ref
        from .defs.ln_classes import SKIP_SYSTEM_DOS

        # 构建 do_ref → [point] 索引 — O(N)
        do_point_index: dict[str, list[dict[str, Any]]] = {}
        for p in discovered:
            p_addr = p.get("address", "")
            p_parsed = parse_ref(p_addr)
            if p_parsed:
                p_ld, p_ln, p_do, _ = p_parsed
                key = f"{p_ld}/{p_ln}.{p_do}"
                do_point_index.setdefault(key, []).append(p)

        seen_dos: set[str] = set()
        do_refs: list[str] = []
        for point in discovered:
            address = point.get("address", "")
            parsed = parse_ref(address)
            if not parsed:
                continue
            ld_inst, ln_name, do_name, _ = parsed
            # 系统 DO (Mod/Beh/Health/NamPlt 等) 无 dU 描述, 跳过
            if do_name in SKIP_SYSTEM_DOS:
                continue
            do_ref = f"{ld_inst}/{ln_name}.{do_name}"
            if do_ref in seen_dos:
                continue
            seen_dos.add(do_ref)
            do_refs.append(do_ref)

        total_dos = len(do_refs)
        description_names = {do_ref: self._discovery.description_da_names(do_ref) for do_ref in do_refs}
        dm = self.datamodels
        batch_descriptions = dm._read_du_descriptions_batch(description_names) if dm else {}
        for index, do_ref in enumerate(do_refs, start=1):
            description_das = description_names[do_ref]
            du_desc = batch_descriptions.get(do_ref, "")
            if not du_desc and description_das != ():
                du_desc = self._read_du_description(do_ref)
            if du_desc:
                # O(1) 索引查找取代 O(N) 内层遍历
                for p in do_point_index.get(do_ref, []):
                    p_addr = p.get("address", "")
                    p["name"] = du_desc
                    self._registry.set_name(p_addr, du_desc)
            if progress is not None:
                progress("descriptions", index, total_dos, f"读取模型描述: {do_ref} ({index}/{total_dos})")

    @property
    def model(self) -> IedModel | None:
        """获取缓存的 IedModel"""
        return self._discovery.model

    def get_discovered_points(self) -> list[dict[str, Any]]:
        """获取当前已映射的测点列表 (委托给 DataModels 插件)"""
        dm = self.datamodels
        if dm:
            return dm.get_discovered_points()
        return []

    def get_discovered_datasets(self) -> list[dict[str, Any]]:
        """获取当前已发现的 DataSet 列表"""
        return list(self._registry.discovered_datasets)

    # ===== 浏览方法 (优先使用已发现的 IedModel，MMS 实时浏览作为 fallback) =====

    def browse_logical_devices(self) -> list[str]:
        """浏览远端 IED 的逻辑设备列表"""
        if self.model is not None:
            return [ld.name for ld in self.model.lds]
        return self._conn.browse_logical_devices()

    def browse_logical_nodes(self, ld: str) -> list[str]:
        """浏览指定逻辑设备下的逻辑节点列表"""
        if self.model is not None:
            for ld_model in self.model.lds:
                if ld_model.name == ld:
                    return [ln.name for ln in ld_model.lns]
        dm = self.datamodels
        if dm:
            return dm.browse_logical_nodes(ld)
        return []

    def browse_data_objects(self, ld: str, ln: str) -> list[dict[str, Any]]:
        """浏览指定逻辑节点下的数据对象列表"""
        if self.model is not None:
            for ld_model in self.model.lds:
                if ld_model.name != ld:
                    continue
                for ln_model in ld_model.lns:
                    if ln_model.name == ln:
                        return [{"name": do.name, "frame_type": do.frame_type} for do in ln_model.dos]
        dm = self.datamodels
        if dm:
            return dm.browse_data_objects(ld, ln)
        return []

    def browse_data_attributes(self, ld: str, ln: str, do_name: str) -> list[dict[str, Any]]:
        """浏览指定数据对象下的数据属性列表"""
        if self.model is not None:
            for ld_model in self.model.lds:
                if ld_model.name != ld:
                    continue
                for ln_model in ld_model.lns:
                    if ln_model.name != ln:
                        continue
                    for do in ln_model.dos:
                        if do.name != do_name:
                            continue
                        return [
                            {
                                "name": da.name,
                                "path": da.name if da.sub_das else da.path,
                                "fc": da.fc,
                                "type": da.iec_type,
                                "mms_type": da.mms_type,
                                "children": [bda.to_flat_dict() for bda in da.sub_das],
                            }
                            for da in do.das
                        ]
        dm = self.datamodels
        if dm:
            return dm.browse_data_attributes(ld, ln, do_name)
        return []

    # ===== DataSet 操作 (委托给 DataSets 插件) =====

    def discover_datasets(self) -> list[dict[str, Any]]:
        """发现所有逻辑设备下的 DataSet 引用 (委托给 DataSets 插件)"""
        ds = self.datasets
        if ds:
            return ds.discover_datasets()
        return []

    def browse_dataset_directory(self, dataset_ref: str) -> list[dict[str, Any]]:
        """浏览 DataSet 目录 (委托给 DataSets 插件)"""
        ds = self.datasets
        if ds:
            return ds.browse_dataset_directory(dataset_ref)
        return []

    def read_dataset_values(self, dataset_ref: str) -> dict[str, Any]:
        """通过 DataSet 一次 MMS 调用读取所有成员的值 (委托给 DataSets 插件)"""
        ds = self.datasets
        if ds:
            return ds.read_dataset_values(dataset_ref)
        return {}

    # ===== 内部辅助 (向后兼容, 供外部代码引用) =====

    def _extract_ln_class(self, ln_name: str) -> str | None:
        """从逻辑节点名提取 lnClass (委托给 defs)"""
        return extract_ln_class(ln_name)

    def _infer_model_name(self):
        """推断 model_name (委托给 connection)"""
        self._conn._infer_model_name()

    def _infer_frame_type_from_do(self, ln_name: str, do_name: str) -> int | None:
        """推断 frame_type (委托给 DataModels 插件)"""
        dm = self.datamodels
        if dm:
            return dm._infer_frame_type_from_do(ln_name, do_name)
        return None

    def _infer_da_path(self, frame_type: int) -> str:
        """推断 DA 路径 (委托给 DataModels 插件)"""
        dm = self.datamodels
        if dm:
            return dm._infer_da_path(frame_type)
        return ""

    def _read_du_description(self, do_ref: str) -> str:
        """读取 du 描述 (委托给 DataModels 插件)"""
        dm = self.datamodels
        if dm:
            return dm._read_du_description(do_ref)
        return ""

    def _discover_da_paths(self, do_ref: str) -> list[tuple]:
        """发现 DA 路径 (委托给 DataModels 插件)"""
        dm = self.datamodels
        if dm:
            return dm._discover_da_paths(do_ref)
        return []

    def _discover_sub_da_paths(self, parent_ref: str, parent_fc: str, parent_path_prefix: str = "") -> list[tuple]:
        """发现子 DA 路径 (委托给 DataModels 插件)"""
        dm = self.datamodels
        if dm:
            return dm._discover_sub_da_paths(parent_ref, parent_fc, parent_path_prefix)
        return []

    def _extract_code_from_address(self, address: str) -> str:
        """提取短编码 (委托给 DataModels 插件)"""
        dm = self.datamodels
        if dm:
            return dm._extract_code_from_address(address)
        return address

    # ===== 读写内部方法 (向后兼容, 供 _read_*_batch 引用) =====

    def _read_floats_batch(self, items, results):
        """批量读取浮点值 (向后兼容, 委托给 core.reader)"""
        from .core.reader import READ_STRATEGIES

        READ_STRATEGIES[MmsType.FLOAT].read_batch(self._conn.connection, items, results)

    def _read_booleans_batch(self, items, results):
        """批量读取布尔值 (向后兼容, 委托给 core.reader)"""
        from .core.reader import READ_STRATEGIES

        READ_STRATEGIES[MmsType.BOOLEAN].read_batch(self._conn.connection, items, results)

    def _read_integers_batch(self, items, results):
        """批量读取整数值 (向后兼容, 委托给 core.reader)"""
        from .core.reader import READ_STRATEGIES

        READ_STRATEGIES[MmsType.INTEGER].read_batch(self._conn.connection, items, results)

    def _read_strings_batch(self, items, results):
        """批量读取字符串值 (向后兼容, 委托给 core.reader)"""
        from .core.reader import READ_STRATEGIES

        READ_STRATEGIES[MmsType.VISIBLE_STRING].read_batch(self._conn.connection, items, results)

    def _read_timestamps_batch(self, items, results):
        """批量读取时标值 (向后兼容, 委托给 core.reader)"""
        from .core.reader import READ_STRATEGIES

        READ_STRATEGIES[MmsType.UTC_TIME].read_batch(self._conn.connection, items, results)

    def _read_unknowns_batch(self, items, results):
        """批量自动探测读取 (向后兼容, 委托给 core.reader)"""
        from .core.reader import READ_STRATEGIES

        READ_STRATEGIES[MmsType.UNKNOWN].read_batch(self._conn.connection, items, results)

    def _read_point_auto_detect(self, ref: str, fc_val) -> Any:
        """自动探测数据类型并读取值 (向后兼容, 委托给 core.reader)"""
        from .core.reader import READ_STRATEGIES

        return READ_STRATEGIES[MmsType.UNKNOWN].read(self._conn.connection, ref, fc_val)

    def _resolve_dataset_ref_with_ld_prefix(self, dataset_ref: str) -> str:
        """解析 DataSet 引用 LD 前缀 (向后兼容, 委托给 connection)"""
        return self._conn._resolve_dataset_ref_with_ld_prefix(dataset_ref)

    # ===== 模型加载 (整改 v2.0: 支持 ICD 文件加载与远程发现两种方式) =====

    def load_model_from_icd(self, icd_path: str, scl_result: Any = None) -> bool:
        """从本地 ICD 文件加载模型

        解析 ICD 文件并构建 PointRegistry，后续 MMS 读写使用此模型。
        不依赖远程 MMS 连接，适合离线加载已知设备模型。

        Args:
            icd_path: ICD 文件路径
            scl_result: 可选，预先解析的 SclImportResult。提供时跳过内部解析步骤。

        Returns:
            是否加载成功
        """
        from .log import log
        from .plugins.scl.service.import_service import SclImportService

        log.info(f"正在从 ICD 文件加载模型: {icd_path}")
        self._offline_model_source = None
        self._discovery.invalidate()
        self._registry.clear()
        self._rcbs_from_icd.clear()
        if self.datasets:
            self.datasets.invalidate_catalog()

        # 1. 解析 ICD 文件（复用外部传入的结果，避免重复解析）
        if scl_result is not None:
            result = scl_result
        else:
            service = SclImportService()
            result = service.import_file(icd_path)
        if not result.is_valid:
            log.error(f"ICD 文件校验失败: {icd_path}, 错误数: {result.validation.error_count}")
            return False

        # 2. 从解析结果构建 PointRegistry
        #    SCL 解析后各个 PointData 的 reg_addr 就是 MMS 引用路径
        point_count = 0
        for point in result.points.yc_points:
            self._registry.set_ref(point.reg_addr, point.reg_addr)
            self._registry.set_fc(point.reg_addr, point.fc)
            self._registry.set_iec_type(point.reg_addr, getattr(point, "iec_type", "") or "float")
            self._registry.set_mms_type(point.reg_addr, getattr(point, "mms_type", "") or "MMS_FLOAT")
            if point.name:
                self._registry.set_name(point.reg_addr, point.name)
            point_count += 1

        for point in result.points.yx_points:
            self._registry.set_ref(point.reg_addr, point.reg_addr)
            self._registry.set_fc(point.reg_addr, point.fc)
            self._registry.set_iec_type(point.reg_addr, getattr(point, "iec_type", "") or "boolean")
            self._registry.set_mms_type(point.reg_addr, getattr(point, "mms_type", "") or "MMS_BOOLEAN")
            if point.name:
                self._registry.set_name(point.reg_addr, point.name)
            point_count += 1

        for point in result.points.yk_points:
            self._registry.set_ref(point.reg_addr, point.reg_addr)
            self._registry.set_fc(point.reg_addr, point.fc)
            self._registry.set_iec_type(point.reg_addr, getattr(point, "iec_type", "") or "boolean")
            self._registry.set_mms_type(point.reg_addr, getattr(point, "mms_type", "") or "MMS_BOOLEAN")
            if point.name:
                self._registry.set_name(point.reg_addr, point.name)
            point_count += 1

        for point in result.points.yt_points:
            self._registry.set_ref(point.reg_addr, point.reg_addr)
            self._registry.set_fc(point.reg_addr, point.fc)
            self._registry.set_iec_type(point.reg_addr, getattr(point, "iec_type", "") or "float")
            self._registry.set_mms_type(point.reg_addr, getattr(point, "mms_type", "") or "MMS_FLOAT")
            if point.name:
                self._registry.set_name(point.reg_addr, point.name)
            point_count += 1

        # 3. 发现 GOOSE 控制块 (从 ICD 文件)
        self._registry.discovered_goose_items.clear()
        for gse in result.goose.gse_controls:
            goose_dict = {
                "go_cb_ref": gse.go_cb_ref,
                "name": gse.name,
                "app_id": gse.app_id or gse.gse_app_id,
                "dat_set": gse.dat_set,
                "data_set_ref": gse.data_set_ref,
                "conf_rev": gse.conf_rev,
                "mac_address": gse.mac_address,
                "dataset_members": gse.dataset_members,
            }
            self._registry.discovered_goose_items.append(goose_dict)

        # 4. 更新 IED 名称
        if result.ied_name:
            self.model_name = result.ied_name

        # ICD 导入过去只填充 PointRegistry 和兼容 DataSet 字典，没有建立
        # IedModel。这样 DO/结构体级 FCDA 只能走保守的注册表投影，q/t/dU
        # 等线上真实成员会被排除；在线发现却能通过完整模型展开，导致两条
        # 路径的 DataSet 覆盖率不一致。安装离线模型，让二者共享同一套
        # DA/BDA 线序投影逻辑。
        if getattr(result, "doc", None) is not None:
            try:
                from .plugins.scl.transformer.server_model_builder import SclServerModelBuilder

                offline_model = SclServerModelBuilder(result.doc).build(host=self.ip, port=self.port)
                self._discovery.install_model(offline_model)
            except Exception as exc:
                log.warning(f"ICD IedModel 构建失败，将使用兼容 DataSet 映射: {exc}")

        # 5. 填充 DataSet 列表（供 UI 展示，不依赖 MMS 连接）
        datasets: list[dict[str, Any]] = []
        seen_ds_refs: set[str] = set()

        # 5a. 纯 DataSet（未被 GOOSE/Report 引用）
        for pd in result.goose.pure_datasets:
            ref = pd.get("ds_ref", "")
            if ref and ref not in seen_ds_refs:
                seen_ds_refs.add(ref)
                members = []
                for entry in pd.get("entries", []):
                    members.append(
                        {
                            "ref": entry.get("name", ""),
                            "fc": entry.get("fc", ""),
                            "iec_type": entry.get("iec_type", ""),
                        }
                    )
                datasets.append(
                    {
                        "ref": ref,
                        "name": pd.get("ds_name", ""),
                        "ld": pd.get("ld_inst", ""),
                        "ln": "",
                        "member_count": pd.get("member_count", 0),
                        "members": members,
                    }
                )

        # 5b. GOOSE 控制块引用的 DataSet
        for gse in result.goose.gse_controls:
            ref = gse.data_set_ref
            if ref and ref not in seen_ds_refs:
                seen_ds_refs.add(ref)
                ld_inst = gse.ld_inst
                ln_class = gse.ln_class
                ds_name = ref.split("$")[-1] if "$" in ref else ""
                members = []
                for m in gse.dataset_members:
                    members.append(
                        {
                            "ref": m.get("fcda_ref", ""),
                            "fc": m.get("fc", ""),
                            "iec_type": "",
                        }
                    )
                datasets.append(
                    {
                        "ref": ref,
                        "name": ds_name,
                        "ld": ld_inst,
                        "ln": ln_class,
                        "member_count": len(members),
                        "members": members,
                    }
                )

        # 5c. Report 引用的 DataSet
        for rc in result.reports.report_controls:
            ref = rc.data_set_ref
            if ref and ref not in seen_ds_refs:
                seen_ds_refs.add(ref)
                ds_name = ref.split("$")[-1] if "$" in ref else rc.dat_set
                members = []
                for entry in rc.entries:
                    members.append(
                        {
                            "ref": entry.get("name", ""),
                            "fc": entry.get("fc", ""),
                            "iec_type": entry.get("iec_type", ""),
                        }
                    )
                datasets.append(
                    {
                        "ref": ref,
                        "name": ds_name,
                        "ld": rc.ld_inst,
                        "ln": rc.ln_name,
                        "member_count": len(members),
                        "members": members,
                    }
                )

        self._registry.discovered_datasets = datasets
        if self.datasets:
            self.datasets.invalidate_catalog()

        # 6. 缓存 RCB 信息（供 UI 展示 Report 列表，不依赖 MMS 连接）
        rcbs: list[dict[str, Any]] = []
        for rc in result.reports.report_controls:
            rcb_ref = f"{rc.ld_inst}/{rc.ln_name}.{rc.name}" if rc.ln_name else ""
            rcbs.append(
                {
                    "ref": rcb_ref,
                    "name": rc.name,
                    "rcb_type": rc.rcb_type,
                    "ld": rc.ld_inst,
                    "ln": rc.ln_name,
                    "rpt_id": rc.rpt_id,
                    "data_set_ref": rc.data_set_ref,
                    "conf_rev": rc.conf_rev,
                    "buf_time": rc.buf_time,
                    "intg_period": rc.intg_period,
                    "trg_ops": rc.trg_ops,
                    "opt_fields": rc.opt_fields,
                    "rpt_ena": False,  # ICD 文件不包含运行状态，默认未使能
                }
            )
        self._rcbs_from_icd = rcbs

        log.info(
            f"ICD 模型加载完成: IED={result.ied_name or icd_path}, "
            f"测点数={point_count}, "
            f"GOOSE={len(result.goose.gse_controls)}, "
            f"DataSet={len(datasets)}, "
            f"Report={len(rcbs)}"
        )

        # 缓存解析结果，供 Device 注册 BasePoint 到 PointManager
        self._last_import_result = result
        self._offline_model_source = "import" if scl_result is not None else "local"
        return True

    def get_icd_points(self) -> dict[str, list]:
        """获取最近一次 ICD 导入的测点列表

        Returns:
            {"yc_points": [...], "yx_points": [...], "yk_points": [...], "yt_points": [...]}
        """
        if self._last_import_result is None:
            return {"yc_points": [], "yx_points": [], "yk_points": [], "yt_points": []}
        return {
            "yc_points": self._last_import_result.points.yc_points,
            "yx_points": self._last_import_result.points.yx_points,
            "yk_points": self._last_import_result.points.yk_points,
            "yt_points": self._last_import_result.points.yt_points,
        }

    def check_model_cache(self) -> dict:
        """检查当前设备是否有可用的模型缓存

        Returns:
            {"cache_exists": bool, "cache_key": str} 字典
        """
        from .model import ModelCache

        cache_key = f"{self.ip}:{self.port}"
        cache = ModelCache.instance()
        return {
            "cache_exists": cache.has(cache_key),
            "cache_key": cache_key,
        }

    def load_model_from_cache(self) -> bool:
        """从缓存加载模型（不进行 MMS 在线发现）

        Returns:
            缓存命中且加载成功返回 True
        """
        from .model import ModelCache
        from .model.registry_bridge import build_registry_from_model

        cache_key = f"{self.ip}:{self.port}"
        cache = ModelCache.instance()

        cached = cache.get(cache_key)
        if cached is None:
            log.warning(f"模型缓存未命中: {cache_key}")
            return False

        log.info(f"从缓存加载模型: {cache_key}")

        # 将缓存模型同步到 _discovery，确保 get_discovered_points() 能正确读取
        self._discovery._model = cached
        self._offline_model_source = "cache"

        # build_registry_from_model 会重建：
        #   - PointRegistry (address → ref/fc/iec_type/mms_type)
        #   - registry.discovered_goose_items
        #   - registry.discovered_datasets
        discovered = build_registry_from_model(cached, self._registry)

        if self.datasets:
            self.datasets.invalidate_catalog()

        # 填充 dU 描述名称（可能无 MMS 连接，失败时静默跳过）
        try:
            if self._conn.is_connected:
                self._fill_du_names(discovered)
            else:
                log.info("从缓存加载模型: 无 MMS 连接，跳过 dU 名称读取")
        except Exception as e:
            log.warning(f"从缓存加载模型: 读取 dU 名称失败（已跳过）: {e}")

        return True

    @property
    def loaded_from_model_cache(self) -> bool:
        """当前内存模型是否来自持久化缓存。"""
        return self._offline_model_source == "cache"

    @property
    def offline_model_requires_validation(self) -> bool:
        """当前模型是否在连接前离线加载，需要在连接后校验。"""
        return self._offline_model_source is not None

    def validate_loaded_model_cache(self) -> bool:
        """兼容入口：连接建立后校验离线加载的模型。"""
        return self.validate_loaded_offline_model()

    def validate_loaded_offline_model(self) -> bool:
        """连接建立后校验缓存、本地加载或导入的离线模型。"""
        source = self._offline_model_source
        if source is None:
            return True

        offline_model = self._discovery.model
        if offline_model is not None and self._cached_model_matches_online_server(offline_model):
            return True

        cache_key = f"{self.ip}:{self.port}"
        if source == "cache":
            from .model import ModelCache

            ModelCache.instance().invalidate(cache_key)
        self._discovery.invalidate()
        self._registry.clear()
        self._last_import_result = None
        self._rcbs_from_icd.clear()
        if self.datasets:
            self.datasets.invalidate_catalog()
        self._offline_model_source = None
        log.warning(f"已清除与当前 IED 不匹配的离线模型及派生点表: source={source}, endpoint={cache_key}")
        return False

    def _cached_model_matches_online_server(self, cached: IedModel) -> bool:
        """连接在线时校验缓存模型是否仍属于当前远端 IED。

        未连接时允许离线加载；已连接时则要求逻辑设备集合完全一致。目录读取
        失败也拒绝加载，因为此时无法证明缓存中的对象引用对当前 association 有效。
        """
        if not self._conn.is_connected:
            return True

        cached_lds = {ld.name for ld in cached.lds if ld.name}
        try:
            online_ld_list = list(self._conn.browse_logical_devices())
            online_lds = set(online_ld_list)
        except Exception as e:
            log.warning(f"模型缓存在线校验失败: 逻辑设备目录读取异常, error={e}")
            return False

        if not online_lds:
            log.warning("模型缓存在线校验失败: 逻辑设备目录为空或读取失败")
            return False

        if cached_lds == online_lds:
            # Offline loading restores the model tree but does not run model
            # discovery, so explicitly restore the runtime domain directory
            # used by reference builders.  Keep the dedicated report
            # association in sync as well.
            self._conn._discovered_lds = online_ld_list
            report_conn = getattr(self, "_report_conn", None)
            if report_conn is not None:
                report_conn._discovered_lds = list(online_ld_list)
            return True

        log.warning(
            "模型缓存与当前 IED 不匹配: "
            f"cached_lds={sorted(cached_lds)}, online_lds={sorted(online_lds)}; "
            "请重新在线发现模型"
        )
        return False

    def _update_model_point_names(self, model: "IedModel", discovered: list[dict[str, Any]]) -> None:
        """将 dU 名称写回模型的 _point_refs，确保缓存文件包含名称"""
        point_refs = getattr(model, "_point_refs", None)
        if not point_refs:
            return
        for point in discovered:
            addr = point.get("address", "")
            name = point.get("name", "")
            if addr and name and addr in point_refs:
                point_refs[addr]["name"] = name

    def remote_discover_model(
        self,
        force_refresh: bool = True,
        progress: DiscoveryProgress | None = None,
    ) -> bool:
        """远程发现模型（通过 MMS 在线遍历）

        用户主动点击"发现模型"时默认强制在线遍历，避免同一 IP:端口
        换了 IED/模型后仍命中上一份缓存。

        Args:
            force_refresh: True 时忽略并刷新进程级模型缓存。
            progress: 可选的发现进度回调。

        Returns:
            是否发现成功
        """
        from .model import ModelCache
        from .model.registry_bridge import build_registry_from_model

        cache_key = f"{self.ip}:{self.port}"

        cache = ModelCache.instance()

        # 1. 显式发现必须反映远端当前状态；只有内部复用场景才允许读缓存。
        if force_refresh:
            cache.invalidate(cache_key)
            self._discovery.invalidate()
            # 清空所有由上一份模型派生的进程内状态。连接级 LD 目录同样
            # 属于缓存；若远端在同一地址切换了 IED，保留它会继续影响
            # DataSet/Report 引用解析，即使 IedModel 本身已经失效。
            self._registry.clear()
            self._conn._discovered_lds.clear()
            report_conn = getattr(self, "_report_conn", None)
            if report_conn is not None:
                report_conn._discovered_lds.clear()
            self._last_import_result = None
            self._offline_model_source = None
            self._rcbs_from_icd.clear()
            datasets = getattr(self, "datasets", None)
            if datasets:
                datasets.invalidate_catalog()
        else:
            cached = cache.get(cache_key)
            if cached is not None:
                if not self._cached_model_matches_online_server(cached):
                    cache.invalidate(cache_key)
                    return False
                self._offline_model_source = None
                log.info(f"远程模型缓存命中: {cache_key}")
                discovered = build_registry_from_model(cached, self._registry)
                if self.datasets:
                    self.datasets.invalidate_catalog()
                self._fill_du_names(discovered)
                return True

        # 2. 确保已连接
        if not self._conn.is_connected:
            log.error("远程发现模型失败: 未连接到服务器")
            return False

        # 3. 在线发现
        operation = self._conn.native_operation()
        guard = operation if hasattr(operation, "__enter__") else contextlib.nullcontext(self._conn.connection)
        with guard as conn:
            if conn is None:
                return False
            model = self._discovery.discover(self._conn, progress=progress)
        report_conn = getattr(self, "_report_conn", None)
        if report_conn is not None:
            report_conn._discovered_lds = list(self._conn._discovered_lds)
        if model is not None:
            if progress:
                progress("building", 0, 1, "正在构建测点索引")
            discovered = build_registry_from_model(model, self._registry)
            if self.datasets:
                self.datasets.invalidate_catalog()
            if progress:
                progress("descriptions", 0, 1, "正在读取模型描述")
            # dU 是 DO 的在线描述值，不包含在目录发现结果中，需要在
            # PointRegistry 建好后按 DO 补读并写回各测点名称。
            self._fill_du_names(discovered, progress=progress)
            # 将 dU 名称写回模型的 _point_refs，确保缓存文件包含名称
            self._update_model_point_names(model, discovered)
            cache.set(cache_key, model)
            self._offline_model_source = None
            if progress:
                progress("descriptions", 1, 1, "模型描述读取完成")
            log.info(f"远程模型发现完成并已缓存: {cache_key}")
            return True

        log.warning("远程模型发现失败")
        return False

    # ===== 模型导出 (委托给 ModelExporter 插件) =====

    @property
    def model_exporter(self) -> ModelExporterPlugin | None:
        """获取模型导出工具实例 (通过插件系统)"""
        return cast(ModelExporterPlugin | None, self._plugins.get("model_exporter"))

    def export_model(self, export_type: str, output_path: str = "", **kwargs) -> str:
        """统一模型导出入口

        Args:
            export_type: 导出类型 (json/csv/icd/xml/tree)
            output_path: 输出文件路径
            **kwargs: 导出器额外参数 (如 ied_name)
        """
        plugin = self.model_exporter
        if plugin:
            return plugin.export(export_type, output_path=output_path, **kwargs)
        return ""

    def export_model_all(self, output_dir: str, ied_name: str = "") -> dict[str, str]:
        """导出所有格式"""
        plugin = self.model_exporter
        if plugin:
            return plugin.export_all(output_dir, ied_name=ied_name)
        return {}
