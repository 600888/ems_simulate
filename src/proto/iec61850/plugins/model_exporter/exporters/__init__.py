"""导出器注册表 — Strategy 模式

统一管理所有导出器，支持按名称查找和扩展。
新增导出格式无需修改消费方。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .csv import CsvExporter
from .icd import IcdExporter
from .json import JsonExporter
from .tree import TreeTextExporter
from .xml import XmlExporter

if TYPE_CHECKING:
    from ....model import IedModel


@runtime_checkable
class ModelExporter(Protocol):
    """导出器协议 — Strategy 模式"""

    def export(self, model: IedModel, output_path: str, **kwargs) -> str:
        """导出模型到文件

        Args:
            model: IedModel 统一模型
            output_path: 输出文件路径

        Returns:
            输出文件路径
        """
        ...


# 使用静态导入，确保 PyInstaller 能发现并打包全部导出器。
_EXPORTER_CLASSES: dict[str, type] = {
    "json": JsonExporter,
    "csv": CsvExporter,
    "icd": IcdExporter,
    "xml": XmlExporter,
    "tree": TreeTextExporter,
}

_cache: dict[str, type] = {}


def get_exporter(export_type: str) -> ModelExporter:
    """获取导出器实例

    Args:
        export_type: 导出类型 (json/csv/icd/xml/tree)

    Returns:
        导出器实例

    Raises:
        ValueError: 不支持的导出类型
    """
    if export_type not in _EXPORTER_CLASSES:
        raise ValueError(f"不支持的导出类型: {export_type}，支持: {', '.join(_EXPORTER_CLASSES)}")

    if export_type not in _cache:
        _cache[export_type] = _EXPORTER_CLASSES[export_type]

    return _cache[export_type]()


def register_exporter(export_type: str, exporter_cls: type) -> None:
    """注册自定义导出器

    Args:
        export_type: 导出类型名称
        exporter_cls: 实现 ModelExporter Protocol 的类
    """
    _cache[export_type] = exporter_cls


def supported_types() -> list[str]:
    """返回所有支持的导出类型"""
    return list(_EXPORTER_CLASSES.keys())
