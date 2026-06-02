"""SCL 服务容器 — DI 容器 (dataclass + 默认参数)

集中管理 SCL 解析流程中的所有依赖，支持 Mock 注入。

用法:
    # 默认容器 (生产)
    container = SclServiceContainer()

    # 注入 Mock (测试)
    container = SclServiceContainer(parser=mock_parser)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..parser.scl_parser import SclParser
from ..transformer.goose_transformer import SclGooseTransformer
from ..transformer.point_transformer import SclPointTransformer
from ..transformer.report_transformer import SclReportTransformer
from ..validator.rules import validate_all

if TYPE_CHECKING:
    from ..model.scl_document import SclDocument


@dataclass
class SclServiceContainer:
    """SCL 服务容器 — 依赖注入

    所有服务都通过此容器获取，方便替换为 Mock 实现。
    使用 dataclass 默认参数实现零配置启动。
    """

    parser: SclParser = field(default_factory=SclParser)

    def parse(self, file_path: str) -> SclDocument:
        """解析 SCL 文件"""
        return self.parser.parse_file(file_path)

    def parse_string(self, xml_string: str) -> SclDocument:
        """解析 SCL XML 字符串"""
        return self.parser.parse_string(xml_string)

    def validate(self, doc: SclDocument):
        """校验 SCL 文档"""
        return validate_all(doc)

    def transform_points(self, doc: SclDocument) -> SclPointTransformer:
        """创建测点转换器"""
        return SclPointTransformer(doc)

    def transform_goose(self, doc: SclDocument) -> SclGooseTransformer:
        """创建 GOOSE 转换器"""
        return SclGooseTransformer(doc)

    def transform_reports(self, doc: SclDocument) -> SclReportTransformer:
        """创建 Report 转换器"""
        return SclReportTransformer(doc)
