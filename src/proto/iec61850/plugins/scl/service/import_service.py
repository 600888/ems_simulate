"""SCL 导入服务 — Facade (解析→校验→转换→持久化)

统一编排 SCL 文件导入流程，替代 IcdPointImporter + IcdGooseImporter。

流程:
  1. SclParser.parse_file() → SclDocument
  2. validate_all() → ValidationResult
  3. SclPointTransformer → 测点数据
  4. SclGooseTransformer → GOOSE 配置
  5. SclReportTransformer → Report 配置
  6. 持久化 (调用方负责)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ....log import log
from ..model.scl_document import SclDocument
from ..transformer.goose_transformer import GooseTransformResult
from ..transformer.point_transformer import PointTransformResult
from ..transformer.report_transformer import ReportTransformResult
from ..validator.result import ValidationResult
from .container import SclServiceContainer


@dataclass
class SclImportResult:
    """SCL 导入完整结果"""

    doc: SclDocument | None = None
    validation: ValidationResult = field(default_factory=ValidationResult)
    points: PointTransformResult = field(default_factory=PointTransformResult)
    goose: GooseTransformResult = field(default_factory=GooseTransformResult)
    reports: ReportTransformResult = field(default_factory=ReportTransformResult)
    ied_name: str = ""

    @property
    def is_valid(self) -> bool:
        return self.validation.is_valid

    def to_dict(self) -> dict[str, Any]:
        """转换为 API 响应格式 (兼容 import-icd 接口)"""
        # 构建 GOOSE publisher/subscription 列表
        publishers = []
        subscriptions = []
        for gse in self.goose.gse_controls:
            publishers.append(gse.to_publisher_dict())
            subscriptions.append(gse.to_subscription_dict())

        return {
            # MMS 测点
            "yc_count": len(self.points.yc_points),
            "yx_count": len(self.points.yx_points),
            "yk_count": len(self.points.yk_points),
            "yt_count": len(self.points.yt_points),
            "total": self.points.total,
            # GOOSE
            "goose": {
                "summary": {
                    "gse_control_count": len(self.goose.gse_controls),
                    "gse_controls": [
                        {
                            "go_cb_ref": g.go_cb_ref,
                            "go_id": g.name,
                            "app_id": g.app_id or g.gse_app_id,
                            "dat_set": g.dat_set,
                            "conf_rev": g.conf_rev,
                            "mac_address": g.mac_address,
                            "dataset_member_count": len(g.dataset_members),
                        }
                        for g in self.goose.gse_controls
                    ],
                },
                "publishers": publishers,
                "subscriptions": subscriptions,
                "engineered_subscriptions": self.goose.engineered_subscriptions,
                "pure_datasets": self.goose.pure_datasets,
                "errors": [],
            },
            # Report
            "report_controls": [
                {
                    "ld_inst": rc.ld_inst,
                    "name": rc.name,
                    "rcb_type": rc.rcb_type,
                    "rpt_id": rc.rpt_id,
                    "dat_set": rc.dat_set,
                    "data_set_ref": rc.data_set_ref,
                    "conf_rev": rc.conf_rev,
                    "buf_time": rc.buf_time,
                    "intg_period": rc.intg_period,
                    "ln_name": rc.ln_name,
                    "trg_ops": rc.trg_ops,
                    "opt_fields": rc.opt_fields,
                    "entries": rc.entries,
                }
                for rc in self.reports.report_controls
            ],
            # 校验
            "validation": {
                "is_valid": self.validation.is_valid,
                "error_count": self.validation.error_count,
                "warning_count": self.validation.warning_count,
                "issues": [str(i) for i in self.validation.issues],
            },
            # IED 信息
            "ied_name": self.ied_name,
        }


class SclImportService:
    """SCL 导入服务 — Facade

    统一编排解析→校验→转换流程。
    支持注入自定义 SclServiceContainer。
    """

    def __init__(self, container: SclServiceContainer | None = None):
        self._container = container or SclServiceContainer()

    def import_file(self, file_path: str, *, validate: bool = True) -> SclImportResult:
        """从 SCL 文件导入

        Args:
            file_path: ICD/SCD/CID 文件路径
            validate: 是否执行校验

        Returns:
            SclImportResult 完整导入结果
        """
        result = SclImportResult()

        # 1. 解析
        try:
            result.doc = self._container.parse(file_path)
        except Exception as e:
            log.error(f"SCL 文件解析失败: {e}")
            result.validation.add_error("parse_error", f"文件解析失败: {e}")
            return result

        # 提取 IED 名称
        ied = result.doc.first_ied
        result.ied_name = ied.name if ied else ""

        # 2. 校验
        if validate:
            result.validation = self._container.validate(result.doc)

        # 3. 转换: 测点
        try:
            point_transformer = self._container.transform_points(result.doc)
            result.points = point_transformer.transform()
        except Exception as e:
            log.warning(f"测点转换失败: {e}")

        # 4. 转换: GOOSE
        try:
            goose_transformer = self._container.transform_goose(result.doc)
            result.goose = goose_transformer.transform()
        except Exception as e:
            log.warning(f"GOOSE 转换失败: {e}")

        # 5. 转换: Report
        try:
            report_transformer = self._container.transform_reports(result.doc)
            result.reports = report_transformer.transform()
        except Exception as e:
            log.warning(f"Report 转换失败: {e}")

        log.info(
            f"SCL 导入完成: IED={result.ied_name}, "
            f"测点={result.points.to_count_tuple()}, "
            f"GSEControl={len(result.goose.gse_controls)}, "
            f"ReportControl={len(result.reports.report_controls)}, "
            f"校验={'通过' if result.validation.is_valid else '有错误'}"
        )

        return result

    def preview_file(self, file_path: str) -> SclImportResult:
        """预览 SCL 文件 (解析+转换，不执行持久化)"""
        return self.import_file(file_path, validate=True)

    def import_string(self, xml_string: str, *, validate: bool = True) -> SclImportResult:
        """从 XML 字符串导入"""
        result = SclImportResult()

        try:
            result.doc = self._container.parse_string(xml_string)
        except Exception as e:
            log.error(f"SCL XML 解析失败: {e}")
            result.validation.add_error("parse_error", f"XML 解析失败: {e}")
            return result

        ied = result.doc.first_ied
        result.ied_name = ied.name if ied else ""

        if validate:
            result.validation = self._container.validate(result.doc)

        try:
            point_transformer = self._container.transform_points(result.doc)
            result.points = point_transformer.transform()
        except Exception as e:
            log.warning(f"测点转换失败: {e}")

        try:
            goose_transformer = self._container.transform_goose(result.doc)
            result.goose = goose_transformer.transform()
        except Exception as e:
            log.warning(f"GOOSE 转换失败: {e}")

        try:
            report_transformer = self._container.transform_reports(result.doc)
            result.reports = report_transformer.transform()
        except Exception as e:
            log.warning(f"Report 转换失败: {e}")

        return result
