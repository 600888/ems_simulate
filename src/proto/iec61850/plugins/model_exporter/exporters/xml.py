"""自定义 XML 模型导出器。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .icd import IcdExporter

if TYPE_CHECKING:
    from ....model import IedModel


class XmlExporter:
    """将 IedModel 导出为非 SCL 的通用 XML 树。"""

    def export(self, model: IedModel, output_path: str, **kwargs) -> str:
        return IcdExporter().export_xml(model, output_path, **kwargs)
