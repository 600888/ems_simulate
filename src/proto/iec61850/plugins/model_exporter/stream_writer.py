"""流式 JSON 写入器 — 零中间 dict 分配

__slots__ 优化内存，链式调用优化可读性。
适用于 5000+ DO 大型模型的流式 JSON 导出。
"""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import Any


class JsonStreamWriter:
    """流式 JSON 写入器

    直接向底层 writer 写入 JSON 片段，避免在内存中构建完整 dict 树。
    内存占用 O(1)，适合大型模型导出。

    Usage:
        with open("output.json", "w") as f:
            w = JsonStreamWriter(f.write)
            w.object_start()
            w.key("name").value("test")
            w.key("items").array_start()
            w.value(1).value(2).value(3)
            w.array_end()
            w.object_end()
    """

    __slots__ = ("_writer", "_first", "_stack")

    def __init__(self, writer: Callable[[str], None]):
        self._writer = writer
        self._first = True
        self._stack: list[bool] = []

    def object_start(self) -> JsonStreamWriter:
        self._write("{")
        self._first = True
        self._stack.append(True)
        return self

    def object_end(self) -> JsonStreamWriter:
        self._stack.pop()
        self._write("}")
        self._first = not self._stack[-1] if self._stack else True
        return self

    def array_start(self) -> JsonStreamWriter:
        self._write("[")
        self._first = True
        self._stack.append(True)
        return self

    def array_end(self) -> JsonStreamWriter:
        self._stack.pop()
        self._write("]")
        self._first = not self._stack[-1] if self._stack else True
        return self

    def key(self, name: str) -> JsonStreamWriter:
        if not self._first:
            self._write(",")
        self._write(f'"{name}":')
        self._first = True
        return self

    def value(self, val: Any) -> JsonStreamWriter:
        if not self._first:
            self._write(",")
        self._write(json.dumps(val, ensure_ascii=False))
        self._first = False
        return self

    def raw(self, chunk: str) -> JsonStreamWriter:
        """写入原始 JSON 片段 (不带逗号分隔)"""
        self._write(chunk)
        return self

    def raw_value(self, chunk: str) -> JsonStreamWriter:
        """写入原始 JSON 值 (带逗号分隔)"""
        if not self._first:
            self._write(",")
        self._write(chunk)
        self._first = False
        return self

    def _write(self, chunk: str) -> None:
        self._writer(chunk)
