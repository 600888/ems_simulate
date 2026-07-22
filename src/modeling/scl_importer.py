"""将现场 ICD/CID 转换为可编辑建模节点图，并保留未知 XML。"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
import re
from typing import Any
import uuid
import xml.etree.ElementTree as ET

SCL_NS = "http://www.iec.ch/61850/2003/SCL"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _namespace(tag: str) -> str:
    match = re.match(r"\{([^}]*)\}", tag)
    return match.group(1) if match else ""


@dataclass(slots=True)
class SclImportResult:
    project: dict[str, Any]
    nodes: list[dict[str, Any]]
    summary: dict[str, Any]
    warnings: list[dict[str, str]]


class SclModelImporter:
    """保真优先的 SCL DOM → 通用节点图适配器。"""

    TAG_KINDS = {
        "Header": "HEADER",
        "History": "HISTORY",
        "Hitem": "HITEM",
        "Communication": "COMMUNICATION",
        "SubNetwork": "SUBNETWORK",
        "ConnectedAP": "CONNECTED_AP",
        "Address": "ADDRESS",
        "P": "P",
        "GSE": "GSE",
        "SMV": "SMV",
        "IED": "IED",
        "Services": "SERVICES",
        "AccessPoint": "ACCESS_POINT",
        "Server": "SERVER",
        "Authentication": "AUTHENTICATION",
        "LDevice": "LDEVICE",
        "LN0": "LN0",
        "LN": "LN",
        "DOI": "DOI",
        "SDI": "SDI",
        "DAI": "DAI",
        "DataSet": "DATASET",
        "FCDA": "FCDA",
        "ReportControl": "REPORT_CONTROL",
        "TrgOps": "TRG_OPS",
        "OptFields": "OPT_FIELDS",
        "RptEnabled": "RPT_ENABLED",
        "ClientLN": "CLIENT_LN",
        "GSEControl": "GSE_CONTROL",
        "SettingControl": "SETTING_CONTROL",
        "Inputs": "INPUTS",
        "ExtRef": "EXT_REF",
        "DataTypeTemplates": "DATA_TYPE_TEMPLATES",
        "LNodeType": "LNODE_TYPE",
        "DOType": "DO_TYPE",
        "DAType": "DA_TYPE",
        "EnumType": "ENUM_TYPE",
        "EnumVal": "ENUM_VALUE",
        "Val": "VAL",
    }

    def parse(
        self,
        content: bytes,
        *,
        filename: str = "model.icd",
        progress: Callable[[str, int, int, str], None] | None = None,
        cancel_check: Callable[[], None] | None = None,
    ) -> SclImportResult:
        self._progress = progress
        self._cancel_check = cancel_check
        self._imported_elements = 0
        if cancel_check:
            cancel_check()
        if progress:
            progress("xml_parse", 0, 4, "Parsing XML")
        if len(content) > 25 * 1024 * 1024:
            raise ValueError("SCL 文件超过 25 MiB 导入上限")
        if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
            raise ValueError("SCL 文件包含被禁用的 DOCTYPE/ENTITY 声明")
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise ValueError(f"XML 不完整或格式错误：{exc}") from exc
        if _local(root.tag) != "SCL":
            raise ValueError("根元素必须为 SCL")
        if progress:
            progress("resource_scan", 1, 4, "Checking XML resource limits")
        element_count = 0
        stack = [(root, 1)]
        while stack:
            element, depth = stack.pop()
            element_count += 1
            if element_count > 300_000:
                raise ValueError("SCL 元素数量超过 300000 个导入上限")
            if depth > 128:
                raise ValueError("SCL XML 层级超过 128 层导入上限")
            stack.extend((child, depth + 1) for child in element)
            if element_count % 1024 == 0 and cancel_check:
                cancel_check()
        if progress:
            progress("model_import", 2, 4, f"Importing {element_count} XML elements")

        namespace = _namespace(root.tag)
        warnings: list[dict[str, str]] = []
        if namespace != SCL_NS:
            warnings.append(
                {"code": "SCL_NAMESPACE_COMPATIBILITY", "message": f"使用了非默认 SCL 名字空间：{namespace or '(无)'}"}
            )

        header = next((child for child in root if _local(child.tag) == "Header"), None)
        first_ied = next((child for child in root if _local(child.tag) == "IED"), None)
        header_id = header.get("id", "") if header is not None else ""
        ied_name = first_ied.get("name", "") if first_ied is not None else ""
        stem = re.sub(r"\.[^.]+$", "", filename)
        code = self._safe_code(header_id or ied_name or stem)
        root_version = root.get("version", "")
        standard_version = "IEC 61850 Ed1" if root_version == "2003" else "IEC 61850 Ed2"
        schema_location = root.get(f"{{{XSI_NS}}}schemaLocation", "")

        nodes: list[dict[str, Any]] = []
        self._nodes: list[dict[str, str]] = []
        used_names: dict[tuple[str | None, str], set[str]] = defaultdict(set)

        def add(kind: str, name: str, parent_id: str | None, attrs: dict[str, Any], order: int) -> str:
            base = name or kind
            candidate = base
            suffix = 2
            key = (parent_id, kind)
            while candidate in used_names[key]:
                candidate = f"{base}_{suffix}"
                suffix += 1
            used_names[key].add(candidate)
            node_id = str(uuid.uuid4())
            nodes.append(
                {
                    "id": node_id,
                    "parent_id": parent_id,
                    "kind": kind,
                    "name": candidate,
                    "sort_order": order,
                    "attributes": attrs,
                }
            )
            return node_id

        root_attrs = {_local(key): value for key, value in root.attrib.items()}
        root_attrs.update(
            {
                "code": code,
                "sourceNamespace": namespace,
                "schemaLocation": schema_location,
                "emitEdition": "version" in root.attrib,
                "sourceFilename": filename,
                "profiles": [],
            }
        )
        root_id = add("ROOT", header_id or stem or "Imported SCL", None, root_attrs, 0)
        self._nodes.append({"id": root_id, "kind": "ROOT"})
        for index, child in enumerate(root):
            self._import_element(child, root_id, index, add, warnings)

        counts = Counter(item["kind"] for item in nodes)
        extensions = counts["EXTENSION"]
        if extensions:
            warnings.append(
                {"code": "SCL_EXTENSIONS_PRESERVED", "message": f"已保真保存 {extensions} 个未知或厂商扩展片段"}
            )
        if progress:
            progress("summary", 4, 4, "Import preview completed")
        return SclImportResult(
            project={
                "name": header_id or stem or "导入模型",
                "code": code,
                "file_type": filename.rsplit(".", 1)[-1].upper() if "." in filename else "ICD",
                "standard_version": standard_version,
                "namespace": namespace,
                "modeling_mode": "IMPORTED",
                "ied_name": ied_name,
            },
            nodes=nodes,
            summary={"node_count": len(nodes), "by_kind": dict(sorted(counts.items())), "extension_count": extensions},
            warnings=warnings,
        )

    def _import_element(self, elem, parent_id, order, add, warnings) -> None:
        self._imported_elements = getattr(self, "_imported_elements", 0) + 1
        if self._imported_elements % 1024 == 0:
            if getattr(self, "_cancel_check", None):
                self._cancel_check()
            if getattr(self, "_progress", None):
                self._progress("model_import", 3, 4, f"Imported {self._imported_elements} XML elements")
        tag = _local(elem.tag)
        parent_kind = next(
            (item["kind"] for item in reversed(getattr(self, "_nodes", [])) if item["id"] == parent_id), ""
        )
        kind = self._kind_for(tag, parent_kind)
        if kind is None or tag == "Private":
            xml = ET.tostring(elem, encoding="unicode", short_empty_elements=True)
            add("EXTENSION", tag, parent_id, {"tag": tag, "xml": xml, "namespace": _namespace(elem.tag)}, order)
            return

        attrs = {_local(key): value for key, value in elem.attrib.items()}
        if kind == "P" or kind in ("VAL", "ENUM_VALUE"):
            attrs["value"] = (elem.text or "").strip()
        elif kind == "SERVICE_CAPABILITY":
            attrs["tag"] = tag
            if len(elem):
                attrs["xml"] = ET.tostring(elem, encoding="unicode", short_empty_elements=True)
        if kind == "SUBNETWORK":
            bit_rate = next((child for child in elem if _local(child.tag) == "BitRate"), None)
            if bit_rate is not None:
                attrs["bitRate"] = (bit_rate.text or "").strip()
                attrs["multiplier"] = bit_rate.get("multiplier", "")
        if kind in ("GSE", "SMV"):
            for xml_name, attr_name in (("MinTime", "minTime"), ("MaxTime", "maxTime")):
                value = next((child for child in elem if _local(child.tag) == xml_name), None)
                if value is not None:
                    attrs[attr_name] = (value.text or "").strip()

        name = self._node_name(kind, tag, attrs)
        node_id = add(kind, name, parent_id, attrs, order)
        self._nodes.append({"id": node_id, "kind": kind})
        if kind == "SERVICE_CAPABILITY" and attrs.get("xml"):
            return
        for child_index, child in enumerate(elem):
            child_tag = _local(child.tag)
            if (kind == "SUBNETWORK" and child_tag == "BitRate") or (
                kind in ("GSE", "SMV") and child_tag in ("MinTime", "MaxTime")
            ):
                continue
            self._import_element(child, node_id, child_index, add, warnings)

    def _kind_for(self, tag: str, parent_kind: str) -> str | None:
        if parent_kind == "SERVICES":
            return "SERVICE_CAPABILITY"
        if tag == "DO" and parent_kind == "LNODE_TYPE":
            return "DO_DEF"
        if tag == "DA" and parent_kind == "DO_TYPE":
            return "DA_DEF"
        if tag == "SDO" and parent_kind == "DO_TYPE":
            return "SDO_DEF"
        if tag == "BDA" and parent_kind == "DA_TYPE":
            return "BDA_DEF"
        return self.TAG_KINDS.get(tag)

    @staticmethod
    def _node_name(kind: str, tag: str, attrs: dict[str, Any]) -> str:
        if kind in ("LNODE_TYPE", "DO_TYPE", "DA_TYPE", "ENUM_TYPE"):
            return str(attrs.get("id") or tag)
        if kind == "LDEVICE":
            return str(attrs.get("inst") or tag)
        if kind == "LN0":
            return "LLN0"
        if kind == "LN":
            return f"{attrs.get('prefix', '')}{attrs.get('lnClass', 'LN')}{attrs.get('inst', '')}"
        if kind == "P":
            return str(attrs.get("type") or "P")
        if kind == "FCDA":
            return ".".join(str(attrs.get(key, "")) for key in ("lnClass", "lnInst", "doName", "daName", "fc")).strip(
                "."
            )
        if kind == "ENUM_VALUE":
            return str(attrs.get("value") or attrs.get("ord") or "EnumVal")
        if kind == "VAL":
            return f"Val_{attrs.get('sGroup', '')}".rstrip("_")
        if kind == "HITEM":
            return str(attrs.get("when") or attrs.get("what") or "Hitem")
        if kind == "SERVICE_CAPABILITY":
            return tag
        return str(attrs.get("name") or tag)

    @staticmethod
    def _safe_code(value: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_-]", "_", value.strip())[:64]
        if not normalized or not normalized[0].isalpha():
            normalized = f"IED_{normalized}"[:64]
        return normalized
