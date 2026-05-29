"""
IEC 61850 MMS 客户端封装 (门面模式)

组合 core/ 和 plugins/ 模块，提供统一的客户端 API。
保持与原有 IEC61850Client 接口完全向后兼容。
"""

import time
from typing import Any, Dict, List, Optional

from .log import log
from .defs import (
    HAS_IEC61850,
    FC_MX, FC_ST, FC_CO,
    IEC_TYPE_FLOAT, IEC_TYPE_BOOLEAN, IEC_TYPE_INTEGER,
    IEC_TYPE_STRING, IEC_TYPE_TIMESTAMP, IEC_TYPE_UNKNOWN,
    YC_LN_CLASSES, YX_LN_CLASSES, YK_LN_CLASSES, YT_LN_CLASSES,
    ALL_LN_CLASSES, SKIP_SYSTEM_DOS, SIGNAL_DOS,
    DA_PATTERNS, DA_PATH_TO_FRAME_TYPE, EXTRA_DA_INFO,
    ENC_DO_DA_TYPE_OVERRIDE, SKIP_DA_NAMES, BDA_TYPE_MAP,
    STRUCT_DA_EXPAND_ONLINE, KNOWN_BDA_FALLBACK_ONLINE,
    is_full_ref, parse_ref,
    infer_fc_from_address, infer_iec_type_from_address,
    extract_ln_class, split_ln_name,
)
from .core import (
    Iec61850Connection,
    Iec61850Reader,
    Iec61850Writer,
    PointRegistry,
    mms_value_to_python,
    get_list_from_linked_list,
)
from .plugins import PluginRegistry

# ===== 向后兼容: 保留旧名称的模块级别别名 =====
# 外部代码可能使用: from iec61850_client import _DA_PATTERNS, _SKIP_DA_NAMES 等
# 直接指向 defs 包导出的对象，避免重复定义
_is_full_ref = is_full_ref
_parse_ref = parse_ref
_DA_PATTERNS = DA_PATTERNS
_DA_PATH_TO_FRAME_TYPE = DA_PATH_TO_FRAME_TYPE
_EXTRA_DA_INFO = EXTRA_DA_INFO
_ENC_DO_DA_TYPE_OVERRIDE = ENC_DO_DA_TYPE_OVERRIDE
_SKIP_DA_NAMES = SKIP_DA_NAMES
_BDA_TYPE_MAP = BDA_TYPE_MAP
_STRUCT_DA_EXPAND_ONLINE = STRUCT_DA_EXPAND_ONLINE
_KNOWN_BDA_FALLBACK_ONLINE = KNOWN_BDA_FALLBACK_ONLINE

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

        # ===== 插件系统 =====
        self._plugins = PluginRegistry()
        self._plugins.initialize_all(self._conn, registry=self._registry, client=self)

        # ===== 懒加载模型导出器 =====
        self._model_exporter = None

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
    def _point_refs(self) -> Dict[str, str]:
        """地址 -> MMS 引用映射 (向后兼容, 委托给 registry)"""
        return self._registry.point_refs

    @property
    def _point_fc(self) -> Dict[str, str]:
        """地址 -> FC 映射 (向后兼容, 委托给 registry)"""
        return self._registry.point_fc

    @property
    def _point_iec_type(self) -> Dict[str, str]:
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

    def read_points_batch(self, addresses: List[str], fc_map: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """批量读取多个测点值 (委托给 Iec61850Reader)"""
        return self._reader.read_batch(addresses, fc_map)

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

    def _mms_value_to_python(self, mms_value, iec_type: str = IEC_TYPE_UNKNOWN) -> Any:
        """将 MmsValue 转换为 Python 类型 (委托给 core)"""
        return mms_value_to_python(mms_value, iec_type)

    def _get_list_from_linked_list(self, linked_list) -> List[str]:
        """从 LinkedList 提取字符串列表 (委托给 core)"""
        return get_list_from_linked_list(linked_list)

    # ===== 插件属性 (按需暴露) =====

    @property
    def datamodels(self):
        """获取 DataModels 插件"""
        return self._plugins.get("datamodels")

    @property
    def datasets(self):
        """获取 DataSets 插件"""
        return self._plugins.get("datasets")

    @property
    def goose(self):
        """获取 GOOSE 插件"""
        return self._plugins.get("goose")

    @property
    def reports(self):
        """获取 Reports 插件"""
        return self._plugins.get("reports")

    # ===== 模型发现 (委托给 DataModels 插件) =====

    def discover_model(self) -> List[Dict[str, Any]]:
        """动态发现并映射服务端的数据模型 (委托给 DataModels 插件)"""
        dm = self.datamodels
        if dm:
            return dm.discover_model()
        return []

    def get_discovered_points(self) -> List[Dict[str, Any]]:
        """获取当前已映射的测点列表 (委托给 DataModels 插件)"""
        dm = self.datamodels
        if dm:
            return dm.get_discovered_points()
        return []

    def get_discovered_datasets(self) -> List[Dict[str, Any]]:
        """获取当前已发现的 DataSet 列表"""
        return list(self._registry.discovered_datasets)

    # ===== 浏览方法 (委托给 DataModels 插件) =====

    def browse_logical_devices(self) -> List[str]:
        """浏览远端 IED 的逻辑设备列表"""
        return self._conn.browse_logical_devices()

    def browse_logical_nodes(self, ld: str) -> List[str]:
        """浏览指定逻辑设备下的逻辑节点列表"""
        dm = self.datamodels
        if dm:
            return dm.browse_logical_nodes(ld)
        return []

    def browse_data_objects(self, ld: str, ln: str) -> List[Dict[str, Any]]:
        """浏览指定逻辑节点下的数据对象列表"""
        dm = self.datamodels
        if dm:
            return dm.browse_data_objects(ld, ln)
        return []

    def browse_data_attributes(self, ld: str, ln: str, do_name: str) -> List[Dict[str, Any]]:
        """浏览指定数据对象下的数据属性列表"""
        dm = self.datamodels
        if dm:
            return dm.browse_data_attributes(ld, ln, do_name)
        return []

    # ===== DataSet 操作 (委托给 DataSets 插件) =====

    def discover_datasets(self) -> List[Dict[str, Any]]:
        """发现所有逻辑设备下的 DataSet 引用 (委托给 DataSets 插件)"""
        ds = self.datasets
        if ds:
            return ds.discover_datasets()
        return []

    def browse_dataset_directory(self, dataset_ref: str) -> List[Dict[str, Any]]:
        """浏览 DataSet 目录 (委托给 DataSets 插件)"""
        ds = self.datasets
        if ds:
            return ds.browse_dataset_directory(dataset_ref)
        return []

    def read_dataset_values(self, dataset_ref: str) -> Dict[str, Any]:
        """通过 DataSet 一次 MMS 调用读取所有成员的值 (委托给 DataSets 插件)"""
        ds = self.datasets
        if ds:
            return ds.read_dataset_values(dataset_ref)
        return {}

    # ===== 内部辅助 (向后兼容, 供外部代码引用) =====

    def _extract_ln_class(self, ln_name: str) -> Optional[str]:
        """从逻辑节点名提取 lnClass (委托给 defs)"""
        return extract_ln_class(ln_name)

    def _infer_model_name(self):
        """推断 model_name (委托给 connection)"""
        self._conn._infer_model_name()

    def _infer_frame_type_from_do(self, ln_name: str, do_name: str) -> Optional[int]:
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

    def _discover_da_paths(self, do_ref: str) -> List[tuple]:
        """发现 DA 路径 (委托给 DataModels 插件)"""
        dm = self.datamodels
        if dm:
            return dm._discover_da_paths(do_ref)
        return []

    def _discover_sub_da_paths(self, parent_ref: str, parent_fc: str, parent_path_prefix: str = "") -> List[tuple]:
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
        """批量读取浮点值 (向后兼容)"""
        from .core.reader import READ_STRATEGIES, IEC_TYPE_FLOAT
        READ_STRATEGIES[IEC_TYPE_FLOAT].read_batch(self._conn.connection, items, results)

    def _read_booleans_batch(self, items, results):
        """批量读取布尔值 (向后兼容)"""
        from .core.reader import READ_STRATEGIES, IEC_TYPE_BOOLEAN
        READ_STRATEGIES[IEC_TYPE_BOOLEAN].read_batch(self._conn.connection, items, results)

    def _read_integers_batch(self, items, results):
        """批量读取整数值 (向后兼容)"""
        from .core.reader import READ_STRATEGIES, IEC_TYPE_INTEGER
        READ_STRATEGIES[IEC_TYPE_INTEGER].read_batch(self._conn.connection, items, results)

    def _read_strings_batch(self, items, results):
        """批量读取字符串值 (向后兼容)"""
        from .core.reader import READ_STRATEGIES, IEC_TYPE_STRING
        READ_STRATEGIES[IEC_TYPE_STRING].read_batch(self._conn.connection, items, results)

    def _read_timestamps_batch(self, items, results):
        """批量读取时标值 (向后兼容)"""
        from .core.reader import READ_STRATEGIES, IEC_TYPE_TIMESTAMP
        READ_STRATEGIES[IEC_TYPE_TIMESTAMP].read_batch(self._conn.connection, items, results)

    def _read_unknowns_batch(self, items, results):
        """批量自动探测读取 (向后兼容)"""
        from .core.reader import READ_STRATEGIES, IEC_TYPE_UNKNOWN
        READ_STRATEGIES[IEC_TYPE_UNKNOWN].read_batch(self._conn.connection, items, results)

    def _read_point_auto_detect(self, ref: str, fc_val) -> Any:
        """自动探测数据类型并读取值 (向后兼容)"""
        from .core.reader import READ_STRATEGIES, IEC_TYPE_UNKNOWN
        return READ_STRATEGIES[IEC_TYPE_UNKNOWN].read(self._conn.connection, ref, fc_val)

    def _resolve_dataset_ref_with_ld_prefix(self, dataset_ref: str) -> str:
        """解析 DataSet 引用 LD 前缀 (向后兼容, 委托给 connection)"""
        return self._conn._resolve_dataset_ref_with_ld_prefix(dataset_ref)

    # ===== 模型导出 (委托给 IEC61850ModelExporter) =====

    @property
    def model_exporter(self):
        """获取模型导出工具实例 (懒加载)"""
        if self._model_exporter is None:
            from .iec61850_model_exporter import IEC61850ModelExporter
            self._model_exporter = IEC61850ModelExporter(self)
        return self._model_exporter

    def discover_server_model(self):
        """动态发现服务端完整数据模型 (结构化)"""
        return self.model_exporter.discover()

    def export_model_json(self, model, output_path, indent=2):
        """导出模型为 JSON"""
        return self.model_exporter.export_json(model, output_path, indent)

    def export_model_csv(self, model, output_path):
        """导出模型为 CSV"""
        return self.model_exporter.export_csv(model, output_path)

    def export_model_tree_text(self, model, output_path):
        """导出模型为树形文本"""
        return self.model_exporter.export_tree_text(model, output_path)

    def export_model_xml(self, model, output_path, pretty=True):
        """导出模型为 XML"""
        return self.model_exporter.export_xml(model, output_path, pretty)

    def export_model_icd(self, model, output_path, ied_name="", pretty=True):
        """导出模型为 ICD"""
        return self.model_exporter.export_icd(model, output_path, ied_name=ied_name, pretty=pretty)

    def export_model_all(self, model, output_dir, ied_name=""):
        """导出所有格式"""
        return self.model_exporter.export_all(model, output_dir, ied_name=ied_name)
