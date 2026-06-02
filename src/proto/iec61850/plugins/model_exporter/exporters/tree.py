"""树形文本导出器 — 直接消费 IedModel

Strategy 模式: 实现 ModelExporter Protocol。
生成人类可读的树形结构文本。
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from ....defs.constants import FRAME_TYPE_DESC

if TYPE_CHECKING:
    from ....model import IedModel


class TreeTextExporter:
    """树形文本导出器 — 直接消费 IedModel"""

    def export(self, model: IedModel, output_path: str, **kwargs) -> str:
        """导出模型为树形文本文件"""
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        lines = self._build_tree(model)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return output_path

    def _build_tree(self, model: IedModel) -> list[str]:
        """构建树形文本行列表"""
        lines = []
        lines.append(f"IEC 61850 Server Model — {model.host}:{model.port}")
        lines.append(f"发现时间: {model.discover_time}")
        lines.append("=" * 80)

        for ld in model.lds:
            lines.append(f"├── LD: {ld.name}")
            for i, ln in enumerate(ld.lns):
                is_last_ln = i == len(ld.lns) - 1
                ln_prefix = "└──" if is_last_ln else "├──"
                ln_indent = "│   " if not is_last_ln else "    "
                ln_class_str = f" [{ln.ln_class}]" if ln.ln_class else ""
                lines.append(f"│   {ln_prefix} LN: {ln.name}{ln_class_str}")

                for j, do in enumerate(ln.dos):
                    is_last_do = (j == len(ln.dos) - 1) and not ln.datasets and not ln.rcb_list
                    do_prefix = "└──" if is_last_do else "├──"
                    ft_desc = FRAME_TYPE_DESC.get(do.frame_type, "未知")
                    lines.append(f"│   {ln_indent}{do_prefix} DO: {do.name} ({ft_desc})")

                    do_indent = ln_indent + ("    " if is_last_do else "│   ")

                    for k, da in enumerate(do.das):
                        is_last_da = (k == len(do.das) - 1) and not da.sub_das
                        da_prefix = "└──" if is_last_da else "├──"
                        fc_str = f" [FC={da.fc}]" if da.fc else ""
                        type_str = f" ({da.iec_type})" if da.iec_type else ""
                        lines.append(f"│   {do_indent}{da_prefix} DA: {da.path}{fc_str}{type_str}")

                        if da.sub_das:
                            bda_indent = do_indent + ("    " if is_last_da else "│   ")
                            for m, bda in enumerate(da.sub_das):
                                is_last_bda = m == len(da.sub_das) - 1
                                bda_prefix = "└──" if is_last_bda else "├──"
                                lines.append(f"│   {bda_indent}{bda_prefix} BDA: {bda.path} ({bda.iec_type})")

                for j, ds in enumerate(ln.datasets):
                    is_last = (j == len(ln.datasets) - 1) and not ln.rcb_list
                    ds_prefix = "└──" if is_last else "├──"
                    lines.append(f"│   {ln_indent}{ds_prefix} DS: {ds.name} ({len(ds.members)} 成员)")
                    ds_indent = ln_indent + ("    " if is_last else "│   ")
                    for m, member in enumerate(ds.members):
                        is_last_m = m == len(ds.members) - 1
                        m_prefix = "└──" if is_last_m else "├──"
                        lines.append(f"│   {ds_indent}{m_prefix} {member.get('ref', '')} [{member.get('fc', '')}]")

                for j, rcb in enumerate(ln.rcb_list):
                    is_last = (j == len(ln.rcb_list) - 1) and not ln.gocb_list
                    rcb_prefix = "└──" if is_last else "├──"
                    lines.append(f"│   {ln_indent}{rcb_prefix} RCB: {rcb.name} ({rcb.rcb_type})")

                for j, gocb in enumerate(ln.gocb_list):
                    is_last = j == len(ln.gocb_list) - 1
                    gocb_prefix = "└──" if is_last else "├──"
                    lines.append(f"│   {ln_indent}{gocb_prefix} GoCB: {gocb.name}")

        lines.append("=" * 80)

        summary = model.summary
        lines.append(
            f"统计: {summary['totalLDs']} LD, {summary['totalLNs']} LN, "
            f"{summary['totalDOs']} DO, {summary['totalDAs']} DA, "
            f"{summary['totalDataSets']} DataSet, {summary['totalRCBs']} RCB, "
            f"{summary['totalGoCBs']} GoCB"
        )

        return lines
