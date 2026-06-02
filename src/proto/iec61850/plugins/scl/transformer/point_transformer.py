"""SclPointTransformer — SclDocument → 测点数据

替代 IcdPointImporter 的核心逻辑:
  SclDocument + TypeResolver → 分类测点列表 (YC/YX/YK/YT)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..model.enums import (
    CDC_CATEGORY_MAP,
    CDC_DEFAULT_FC,
    PointCategory,
)
from ..model.scl_document import SclDocument, SclDOI, SclLDevice, SclLN
from ..parser.type_resolver import TypeResolver


@dataclass
class PointData:
    """测点数据"""
    code: str = ""
    name: str = ""
    reg_addr: str = ""
    cdc: str = ""
    da_name: str = ""
    fc: str = ""
    category: PointCategory = PointCategory.YC


@dataclass
class PointTransformResult:
    """测点转换结果"""
    yc_points: list[PointData] = field(default_factory=list)
    yx_points: list[PointData] = field(default_factory=list)
    yk_points: list[PointData] = field(default_factory=list)
    yt_points: list[PointData] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.yc_points) + len(self.yx_points) + len(self.yk_points) + len(self.yt_points)

    def to_count_tuple(self) -> tuple[int, int, int, int]:
        return (len(self.yc_points), len(self.yx_points), len(self.yk_points), len(self.yt_points))


class SclPointTransformer:
    """SCL 测点转换器 — SclDocument → 分类测点列表"""

    def __init__(self, doc: SclDocument):
        self._doc = doc
        self._resolver = TypeResolver(doc)

    def transform(self) -> PointTransformResult:
        """执行转换"""
        result = PointTransformResult()

        for ied in self._doc.ieds:
            for ap in ied.access_points:
                if not ap.server:
                    continue
                for ld in ap.server.ldevices:
                    for ln in [ld.ln0] + ld.lns if ld.ln0 else ld.lns:
                        self._transform_ln(ln, ld, result)

        return result

    def _transform_ln(self, ln: SclLN, ld: SclLDevice, result: PointTransformResult) -> None:
        """转换单个 LN"""
        if not ln.ln_type:
            return

        ln_type = self._doc.get_ln_node_type(ln.ln_type)
        if ln_type is None:
            return

        # DOI 索引
        doi_map: dict[str, SclDOI] = {doi.name: doi for doi in ln.dois}

        for do_def in ln_type.dos:
            do_type = self._doc.get_do_type(do_def.type_id)
            if do_type is None:
                continue

            cdc = do_type.cdc
            if cdc not in CDC_CATEGORY_MAP:
                continue

            category = CDC_CATEGORY_MAP[cdc]
            ref_prefix = f"{ld.inst}/{ln.ln_name}.{do_def.name}"

            # 获取 DO 描述
            doi = doi_map.get(do_def.name)
            do_desc = self._resolver.get_do_desc(do_def.name, do_type, doi)

            # 获取主值 DA 路径
            main_da_path = self._resolver.get_value_da_path(do_def.type_id, cdc)
            if main_da_path:
                fc = CDC_DEFAULT_FC.get(cdc, "")
                point = PointData(
                    code=f"{ld.inst}_{ln.ln_name}_{do_def.name}_{main_da_path.replace('.', '_')}",
                    name=do_desc,
                    reg_addr=f"{ref_prefix}.{main_da_path}",
                    cdc=cdc,
                    da_name=main_da_path,
                    fc=fc,
                    category=category,
                )
                self._add_point(result, point, category)

            # 额外 DA 测点
            all_das = self._resolver.collect_all_das(do_def.type_id, cdc)
            main_fc = CDC_DEFAULT_FC.get(cdc, "")
            for da_info in all_das:
                da_path = da_info["path"]
                da_fc = da_info["fc"]
                if da_path == main_da_path:
                    continue
                # 只收集相关 FC 的 DA
                if category == PointCategory.YC and da_fc in ("MX", "ST", "DC"):
                    pass
                elif category == PointCategory.YX and da_fc in ("ST", "MX", "DC"):
                    pass
                elif category in (PointCategory.YK, PointCategory.YT) and da_fc in ("CO", "ST", "DC"):
                    pass
                else:
                    continue

                point = PointData(
                    code=f"{ld.inst}_{ln.ln_name}_{do_def.name}_{da_path.replace('.', '_')}",
                    name=do_desc,
                    reg_addr=f"{ref_prefix}.{da_path}",
                    cdc=cdc,
                    da_name=da_path,
                    fc=da_fc,
                    category=category,
                )
                self._add_point(result, point, category)

    @staticmethod
    def _add_point(result: PointTransformResult, point: PointData, category: PointCategory) -> None:
        if category == PointCategory.YC:
            result.yc_points.append(point)
        elif category == PointCategory.YX:
            result.yx_points.append(point)
        elif category == PointCategory.YK:
            result.yk_points.append(point)
        elif category == PointCategory.YT:
            result.yt_points.append(point)
