"""命名空间检测助手

ICD 文件可能带或不带 SCL 命名空间:
  有: <SCL xmlns="http://www.iec.ch/61850/2003/SCL">
  无: <SCL>

本模块自动检测并统一处理。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET


class NamespaceHelper:
    """SCL 命名空间检测与标签构造"""

    __slots__ = ("_ns_prefix",)

    def __init__(self, ns_prefix: str = ""):
        """读取 XML 根节点的命名空间，并生成后续查询使用的标签前缀。"""
        self._ns_prefix = ns_prefix

    @classmethod
    def from_root(cls, root: ET.Element) -> NamespaceHelper:
        """从 XML 根元素自动检测命名空间"""
        tag = root.tag
        if tag.startswith("{"):
            ns = tag.split("}")[0] + "}"
            return cls(ns_prefix=ns)
        return cls(ns_prefix="")

    @property
    def ns_prefix(self) -> str:
        """返回SCL 命名空间助手当前的NSprefix。"""
        return self._ns_prefix

    @property
    def has_namespace(self) -> bool:
        """判断SCL 命名空间助手是否处于namespace。"""
        return bool(self._ns_prefix)

    def tag(self, name: str) -> str:
        """构造完整 tag"""
        if self._ns_prefix:
            return f"{self._ns_prefix}{name}"
        return name

    def find(self, parent: ET.Element, name: str) -> ET.Element | None:
        """查找首个匹配节点，并自动为标签补充 SCL XML 命名空间。"""
        return parent.find(self.tag(name))

    def findall(self, parent: ET.Element, name: str) -> list[ET.Element]:
        """查找当前元素下全部匹配节点，并自动处理 SCL XML 命名空间。"""
        return parent.findall(self.tag(name))

    def iter(self, parent: ET.Element, name: str):
        """迭代全部匹配节点，并自动为标签补充 SCL XML 命名空间。"""
        return parent.iter(self.tag(name))

    def get_text(self, elem: ET.Element | None, attr: str, default: str = "") -> str:
        """安全获取元素属性"""
        if elem is None:
            return default
        return elem.get(attr, default)

    @staticmethod
    def p_value(address_elem: ET.Element | None, p_type: str, ns: NamespaceHelper | None = None) -> str:
        """从 Address/P 元素获取指定 type 的值"""
        if address_elem is None:
            return ""
        tag = ns.tag("P") if ns else "P"
        for p in address_elem.findall(tag):
            if p.get("type", "") == p_type:
                return (p.text or "").strip()
        return ""
