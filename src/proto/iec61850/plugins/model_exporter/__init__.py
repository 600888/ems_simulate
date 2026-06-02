"""ModelExporter 插件 - 多格式模型导出

v3.0: 导出器拆分为 Strategy 模式 (exporters/ 子包)，直接消费 IedModel。
新增导出格式只需创建新类 + register_exporter()，无需修改本插件。
"""

import os
from typing import TYPE_CHECKING, Any

from ...log import log
from ...defs.constants import HAS_IEC61850

if TYPE_CHECKING:
    from ...iec61850_client import IEC61850Client


class ModelExporterPlugin:
    """ModelExporter 插件

    提供多格式导出（JSON/CSV/XML/ICD/树形文本），直接消费 IedModel。

    v3.0 变更:
    - 导出器拆分为 Strategy 模式 (exporters/ 子包)
    - 直接消费 IedModel，无需中间转换
    - 统一使用 export() 入口
    """

    def __init__(self):
        self._connection = None
        self._client: IEC61850Client | None = None
        self._initialized = False

    @property
    def name(self) -> str:
        return "model_exporter"

    @property
    def available(self) -> bool:
        return HAS_IEC61850

    def initialize(self, connection: Any, **kwargs) -> None:
        self._connection = connection
        self._client = kwargs.get("client")
        self._initialized = True
        log.info("ModelExporter 插件已初始化")

    def shutdown(self) -> None:
        self._connection = None
        self._client = None
        self._initialized = False

    # ===== IedModel 获取 =====

    def _get_ied_model(self):
        """获取缓存的 IedModel

        优先级:
        1. client 缓存的 IedModel
        2. 无缓存 → 返回 None
        """
        if self._client and hasattr(self._client, 'model') and self._client.model is not None:
            return self._client.model
        return None

    # ===== 导出 =====

    def export(self, export_type: str, output_path: str = "", **kwargs) -> str:
        """统一导出入口 — 使用 Strategy 导出器

        Args:
            export_type: 导出类型 (json/csv/icd/xml/tree)
            output_path: 输出文件路径

        Raises:
            RuntimeError: 未初始化或无 IedModel 缓存
            ValueError: 不支持的导出类型
        """
        from .exporters import get_exporter

        ied_model = self._get_ied_model()
        if ied_model is None:
            raise RuntimeError("无 IedModel 缓存，请先连接 IED 设备")

        if export_type == "xml":
            # XML 由 IcdExporter.export_xml 单独处理
            from .exporters.icd import IcdExporter

            return IcdExporter().export_xml(ied_model, output_path)

        exporter = get_exporter(export_type)
        if export_type == "icd":
            return exporter.export(ied_model, output_path, ied_name=kwargs.get("ied_name", ""))
        return exporter.export(ied_model, output_path, **kwargs)

    def export_all(self, output_dir: str, ied_name: str = "") -> dict[str, str]:
        """导出所有格式到指定目录

        Returns:
            {格式: 文件路径} 字典
        """
        from .exporters import get_exporter

        ied_model = self._get_ied_model()
        if ied_model is None:
            raise RuntimeError("无 IedModel 缓存，请先连接 IED 设备")

        os.makedirs(output_dir, exist_ok=True)
        base_name = f"iec61850_model_{ied_model.host}_{ied_model.port}"
        results = {}

        for export_type, ext in [("json", ".json"), ("csv", ".csv"), ("tree", ".txt")]:
            path = os.path.join(output_dir, f"{base_name}{ext}")
            exporter = get_exporter(export_type)
            exporter.export(ied_model, path)
            results[export_type] = path

        # XML + ICD (都由 IcdExporter 提供)
        from .exporters.icd import IcdExporter

        icd_exporter = IcdExporter()
        xml_path = os.path.join(output_dir, f"{base_name}.xml")
        icd_exporter.export_xml(ied_model, xml_path)
        results["xml"] = xml_path

        icd_path = os.path.join(output_dir, f"{base_name}.icd")
        icd_exporter.export(ied_model, icd_path, ied_name=ied_name)
        results["icd"] = icd_path

        return results
