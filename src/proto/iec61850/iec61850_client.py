"""
IEC 61850 MMS 客户端封装 (门面模式)

组合 core/ 和 plugins/ 模块，提供统一的客户端 API。
保持与原有 IEC61850Client 接口完全向后兼容。

v3.0 变更: 集成 ModelDiscoveryService，连接时一次发现 → IedModel 缓存 → 多处消费。
"""

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
from .model import IedModel
from .model.discovery import ModelDiscoveryService
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
        self._registry = PointRegistry(model_name, ld_name)
        self._reader = Iec61850Reader(self._conn, self._registry)
        self._writer = Iec61850Writer(self._conn, self._registry)

        # ===== 统一模型发现服务 =====
        self._discovery = ModelDiscoveryService()

        # ===== 插件系统 =====
        self._plugins = PluginRegistry(auto_register=False)
        _register_builtin_plugins(self._plugins)
        self._plugins.initialize_all(self._conn, registry=self._registry, client=self)

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
        return self._conn.connect(
            auto_discover=auto_discover,
            discover_callback=self.discover_model if auto_discover else None,
        )

    def disconnect(self):
        """断开连接"""
        self._discovery.invalidate()
        self._conn.disconnect()

    @property
    def is_connected(self) -> bool:
        return self._conn.is_connected

    # ===== 测点管理 (委托给 PointRegistry) =====

    def add_point(self, address, frame_type: int = 0, fc: str = "") -> str:
        """注册测点引用路径 (委托给 PointRegistry)"""
        return self._registry.add_point(address, frame_type, fc)

    # ===== 读写 (委托给 Iec61850Reader/Iec61850Writer) =====

    def read_point(self, address, fc: str = "") -> Any:
        """读取测点值 (委托给 Iec61850Reader)"""
        return self._reader.read(address, fc)

    def read_points_batch(self, addresses: list[str], fc_map: dict[str, str] | None = None) -> dict[str, Any]:
        """批量读取多个测点值 (委托给 Iec61850Reader)"""
        return self._reader.read_batch(addresses, fc_map)

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
        from .defs.address import parse_ref

        parsed = parse_ref(address)
        if not parsed:
            return MetadataInfo()
        ld_inst, ln_name, do_name, _ = parsed
        do_ref = f"{ld_inst}/{ln_name}.{do_name}"

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
        return cast(DataModelsPlugin | None, self._plugins.get("datamodels"))

    @property
    def datasets(self) -> DataSetsPlugin | None:
        """获取 DataSets 插件"""
        return cast(DataSetsPlugin | None, self._plugins.get("datasets"))

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
        model = self._discovery.discover(self._conn)

        # 从 IedModel 派生 PointRegistry
        discovered = build_registry_from_model(model, self._registry)

        # 补充 dU 描述名称 (与 DataModelsPlugin._read_du_description 一致)
        self._fill_du_names(discovered)

        return discovered

    def _fill_du_names(self, discovered: list[dict[str, Any]]) -> None:
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

            du_desc = self._read_du_description(do_ref)
            if not du_desc:
                continue

            # O(1) 索引查找取代 O(N) 内层遍历
            for p in do_point_index.get(do_ref, []):
                p_addr = p.get("address", "")
                p["name"] = du_desc
                self._registry.set_name(p_addr, du_desc)

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

    # ===== 浏览方法 (委托给 DataModels 插件) =====

    def browse_logical_devices(self) -> list[str]:
        """浏览远端 IED 的逻辑设备列表"""
        return self._conn.browse_logical_devices()

    def browse_logical_nodes(self, ld: str) -> list[str]:
        """浏览指定逻辑设备下的逻辑节点列表"""
        dm = self.datamodels
        if dm:
            return dm.browse_logical_nodes(ld)
        return []

    def browse_data_objects(self, ld: str, ln: str) -> list[dict[str, Any]]:
        """浏览指定逻辑节点下的数据对象列表"""
        dm = self.datamodels
        if dm:
            return dm.browse_data_objects(ld, ln)
        return []

    def browse_data_attributes(self, ld: str, ln: str, do_name: str) -> list[dict[str, Any]]:
        """浏览指定数据对象下的数据属性列表"""
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

        READ_STRATEGIES[IecType.FLOAT].read_batch(self._conn.connection, items, results)

    def _read_booleans_batch(self, items, results):
        """批量读取布尔值 (向后兼容, 委托给 core.reader)"""
        from .core.reader import READ_STRATEGIES

        READ_STRATEGIES[IecType.BOOLEAN].read_batch(self._conn.connection, items, results)

    def _read_integers_batch(self, items, results):
        """批量读取整数值 (向后兼容, 委托给 core.reader)"""
        from .core.reader import READ_STRATEGIES

        READ_STRATEGIES[IecType.INTEGER].read_batch(self._conn.connection, items, results)

    def _read_strings_batch(self, items, results):
        """批量读取字符串值 (向后兼容, 委托给 core.reader)"""
        from .core.reader import READ_STRATEGIES

        READ_STRATEGIES[IecType.STRING].read_batch(self._conn.connection, items, results)

    def _read_timestamps_batch(self, items, results):
        """批量读取时标值 (向后兼容, 委托给 core.reader)"""
        from .core.reader import READ_STRATEGIES

        READ_STRATEGIES[IecType.TIMESTAMP].read_batch(self._conn.connection, items, results)

    def _read_unknowns_batch(self, items, results):
        """批量自动探测读取 (向后兼容, 委托给 core.reader)"""
        from .core.reader import READ_STRATEGIES

        READ_STRATEGIES[IecType.UNKNOWN].read_batch(self._conn.connection, items, results)

    def _read_point_auto_detect(self, ref: str, fc_val) -> Any:
        """自动探测数据类型并读取值 (向后兼容, 委托给 core.reader)"""
        from .core.reader import READ_STRATEGIES

        return READ_STRATEGIES[IecType.UNKNOWN].read(self._conn.connection, ref, fc_val)

    def _resolve_dataset_ref_with_ld_prefix(self, dataset_ref: str) -> str:
        """解析 DataSet 引用 LD 前缀 (向后兼容, 委托给 connection)"""
        return self._conn._resolve_dataset_ref_with_ld_prefix(dataset_ref)

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
