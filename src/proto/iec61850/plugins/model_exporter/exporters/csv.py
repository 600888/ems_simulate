"""CSV 导出器 — 直接消费 IedModel

Strategy 模式: 实现 ModelExporter Protocol。
增量逐行写入，内存 O(1)。
"""

from __future__ import annotations

import csv
import os
from typing import TYPE_CHECKING

from ....defs.constants import FRAME_TYPE_DESC

if TYPE_CHECKING:
    from ....model import IedModel


class CsvExporter:
    """CSV 导出器 — 增量逐行写入"""

    # CSV 表头
    HEADER = [
        "逻辑设备(LD)",
        "逻辑节点(LN)",
        "LN类",
        "数据对象(DO)",
        "DA路径",
        "FC",
        "数据类型",
        "帧类型",
        "帧类型描述",
        "完整引用",
    ]

    def export(self, model: IedModel, output_path: str, **kwargs) -> str:
        """导出模型为 CSV 文件 (扁平化测点表)

        CSV 列: LD, LN, LN类, DO, DA路径, FC, 数据类型, 帧类型, 帧类型描述, 完整引用
        """
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self.HEADER)

            for row in self._iter_rows(model):
                writer.writerow(row)

        return output_path

    def _iter_rows(self, model: IedModel):
        """逐行生成 CSV 数据 — 惰性求值"""
        for ld, ln, do, da in model.iter_da_leaves():
            ft = do.frame_type
            ft_desc = FRAME_TYPE_DESC.get(ft, "未知")
            full_ref = f"{do.ref}.{da.path}"

            yield [
                ld.name,
                ln.name,
                ln.ln_class or "",
                do.name,
                da.path,
                da.fc,
                da.iec_type,
                str(ft),
                ft_desc,
                full_ref,
            ]

            # BDA 展开
            for bda in da.sub_das:
                yield [
                    ld.name,
                    ln.name,
                    ln.ln_class or "",
                    do.name,
                    bda.path,
                    bda.fc or da.fc,
                    bda.iec_type,
                    str(ft),
                    ft_desc,
                    f"{do.ref}.{bda.path}",
                ]
