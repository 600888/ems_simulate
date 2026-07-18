"""内置校验规则

4 个核心规则:
1. IedExistenceRule — 检查 IED 是否存在
2. TypeReferenceIntegrityRule — 检查类型引用完整性
3. DataSetNotEmptyRule — 检查 DataSet 非空
4. GoCBDataSetReferenceRule — 检查 GSEControl 引用的 DataSet 存在
"""

from __future__ import annotations

from ..model.scl_document import SclDocument
from .result import ValidationResult
from .rules import register_rule


@register_rule
class IedExistenceRule:
    """检查 IED 是否存在"""

    @property
    def rule_id(self) -> str:
        """返回IedExistenceRule当前的RULE标识。"""
        return "ied_existence"

    @property
    def description(self) -> str:
        """返回IedExistenceRule当前的说明。"""
        return "检查 SCL 文件是否包含至少一个 IED 定义"

    def validate(self, doc: SclDocument) -> ValidationResult:
        """按当前校验规则检查 SCL 文档，并返回发现的错误、警告和提示。"""
        result = ValidationResult()
        if not doc.ieds:
            result.add_error(self.rule_id, "SCL 文件中未找到任何 IED 定义")
        return result


@register_rule
class TypeReferenceIntegrityRule:
    """检查类型引用完整性 — LNodeType/DOType/DAType 的 type 引用是否可解析"""

    @property
    def rule_id(self) -> str:
        """返回TypeReferenceIntegrityRule当前的RULE标识。"""
        return "type_reference_integrity"

    @property
    def description(self) -> str:
        """返回TypeReferenceIntegrityRule当前的说明。"""
        return "检查 DataTypeTemplates 中类型引用的完整性"

    def validate(self, doc: SclDocument) -> ValidationResult:
        """按当前校验规则检查 SCL 文档，并返回发现的错误、警告和提示。"""
        result = ValidationResult()
        dtt = doc.data_type_templates

        for lt_id, lt in dtt.ln_node_types.items():
            for do in lt.dos:
                if do.type_id and do.type_id not in dtt.do_types:
                    result.add_warning(
                        self.rule_id,
                        f"LNodeType '{lt_id}' 的 DO '{do.name}' 引用了不存在的 DOType '{do.type_id}'",
                        location=f"LNodeType.{lt_id}",
                    )

        for dt_id, dt in dtt.do_types.items():
            for da in dt.das:
                if da.b_type == "Struct" and da.type_id and da.type_id not in dtt.da_types:
                    result.add_warning(
                        self.rule_id,
                        f"DOType '{dt_id}' 的 DA '{da.name}' 引用了不存在的 DAType '{da.type_id}'",
                        location=f"DOType.{dt_id}",
                    )
            for sdo in dt.sdos:
                if sdo.type_id and sdo.type_id not in dtt.do_types:
                    result.add_warning(
                        self.rule_id,
                        f"DOType '{dt_id}' 的 SDO '{sdo.name}' 引用了不存在的 DOType '{sdo.type_id}'",
                        location=f"DOType.{dt_id}",
                    )

        for dat_id, dat in dtt.da_types.items():
            for bda in dat.bdas:
                if bda.b_type == "Struct" and bda.type_id and bda.type_id not in dtt.da_types:
                    result.add_warning(
                        self.rule_id,
                        f"DAType '{dat_id}' 的 BDA '{bda.name}' 引用了不存在的 DAType '{bda.type_id}'",
                        location=f"DAType.{dat_id}",
                    )
                if bda.b_type == "Enum" and bda.type_id and bda.type_id not in dtt.enum_types:
                    result.add_warning(
                        self.rule_id,
                        f"DAType '{dat_id}' 的 BDA '{bda.name}' 引用了不存在的 EnumType '{bda.type_id}'",
                        location=f"DAType.{dat_id}",
                    )

        return result


@register_rule
class DataSetNotEmptyRule:
    """检查 DataSet 非空"""

    @property
    def rule_id(self) -> str:
        """返回DataSetNotEmptyRule当前的RULE标识。"""
        return "dataset_not_empty"

    @property
    def description(self) -> str:
        """返回DataSetNotEmptyRule当前的说明。"""
        return "检查 DataSet 至少包含一个 FCDA"

    def validate(self, doc: SclDocument) -> ValidationResult:
        """按当前校验规则检查 SCL 文档，并返回发现的错误、警告和提示。"""
        result = ValidationResult()
        for ied in doc.ieds:
            for ap in ied.access_points:
                if not ap.server:
                    continue
                for ld in ap.server.ldevices:
                    for ln in [ld.ln0] + ld.lns if ld.ln0 else ld.lns:
                        for ds in ln.datasets:
                            if not ds.members:
                                result.add_warning(
                                    self.rule_id,
                                    f"DataSet '{ds.name}' 为空 (无 FCDA)",
                                    location=f"{ied.name}.{ld.inst}.{ln.ln_name}",
                                )
        return result


@register_rule
class GoCBDataSetReferenceRule:
    """检查 GSEControl 引用的 DataSet 存在"""

    @property
    def rule_id(self) -> str:
        """返回GoCBDataSetReferenceRule当前的RULE标识。"""
        return "gocb_dataset_reference"

    @property
    def description(self) -> str:
        """返回GoCBDataSetReferenceRule当前的说明。"""
        return "检查 GSEControl 的 datSet 属性引用的 DataSet 是否存在"

    def validate(self, doc: SclDocument) -> ValidationResult:
        """按当前校验规则检查 SCL 文档，并返回发现的错误、警告和提示。"""
        result = ValidationResult()
        for ied in doc.ieds:
            for ap in ied.access_points:
                if not ap.server:
                    continue
                for ld in ap.server.ldevices:
                    for ln in [ld.ln0] + ld.lns if ld.ln0 else ld.lns:
                        ds_names = {ds.name for ds in ln.datasets}
                        for gse in ln.gse_controls:
                            if gse.dat_set and gse.dat_set not in ds_names:
                                result.add_error(
                                    self.rule_id,
                                    f"GSEControl '{gse.name}' 引用的 DataSet '{gse.dat_set}' 不存在",
                                    location=f"{ied.name}.{ld.inst}.{ln.ln_name}",
                                )
        return result
