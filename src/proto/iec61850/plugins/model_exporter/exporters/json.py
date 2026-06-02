"""JSON 导出器 — 直接消费 IedModel

Strategy 模式: 实现 ModelExporter Protocol。
支持标准 JSON 导出和流式 JSON 导出 (大模型 O(1) 内存)。
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ....model import IedModel


class JsonExporter:
    """JSON 导出器 — 直接消费 IedModel"""

    def export(self, model: IedModel, output_path: str, *, indent: int = 2, **kwargs) -> str:
        """导出完整 JSON 文件

        Args:
            model: IedModel 统一模型
            output_path: 输出文件路径
            indent: JSON 缩进级别
        """
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(model.to_dict(), f, ensure_ascii=False, indent=indent)
        return output_path

    def export_streaming(self, model: IedModel, output_path: str, **kwargs) -> str:
        """流式 JSON 导出 — 内存 O(1)

        逐块写入文件，避免在内存中构建完整的 dict 树。
        适合 5000+ DO 的大型模型。
        """
        from .stream_writer import JsonStreamWriter

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            writer = JsonStreamWriter(f.write)

            writer.object_start()
            writer.key("host").value(model.host)
            writer.key("port").value(model.port)
            writer.key("discover_time").value(model.discover_time)

            # logicalDevices 数组
            writer.key("logicalDevices").array_start()

            for i, ld in enumerate(model.lds):
                if i > 0:
                    writer._write(",")
                json.dump(ld.to_dict(), f, ensure_ascii=False)

            writer.array_end()

            # summary 对象
            writer.key("summary")
            json.dump(model.summary, f, ensure_ascii=False)

            writer.object_end()

        return output_path
