"""ICD/SCL 导出器 — 直接消费 IedModel

Strategy 模式: 实现 ModelExporter Protocol。
生成符合 IEC 61850-6 SCL Schema 的 XML 文件。

支持两种导出:
1. ICD 标准格式 (SCL Schema)
2. 自定义 XML 格式

迁移自 IEC61850ModelExporter._model_to_scl_dict / _model_to_xml_dict，
改为直接消费 IedModel。
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any

import xmltodict

from ....defs.constants import FRAME_TYPE_DESC, IecType

# 空元素转自闭合标签: 匹配 <tag ...></tag> → <tag .../>
_RE_EMPTY_ELEMENT = re.compile(r"<(\w+)([^>]*)></\1>")

# DOType/DAType 类型模板 ID 计数器
_do_type_counter: dict[str, int] = {}
_da_type_counter: dict[str, int] = {}


def _reset_type_counters() -> None:
    """重置类型模板计数器（每次导出前调用）"""
    _do_type_counter.clear()
    _da_type_counter.clear()


def _next_do_type_id(cdc: str) -> str:
    """生成全局唯一的 DOType ID"""
    _do_type_counter[cdc] = _do_type_counter.get(cdc, 0) + 1
    return f"_T_{cdc}_{_do_type_counter[cdc]}"


def _next_da_type_id(prefix: str = "STRUCT") -> str:
    """生成全局唯一的 DAType ID"""
    _da_type_counter[prefix] = _da_type_counter.get(prefix, 0) + 1
    return f"_T_{prefix}_{_da_type_counter[prefix]}"


if TYPE_CHECKING:
    from ....model import IedModel


class IcdExporter:
    """ICD/SCL 导出器 — 直接消费 IedModel"""

    def export(
        self,
        model: IedModel,
        output_path: str,
        *,
        ied_name: str = "",
        pretty: bool = True,
        do_descriptions: dict[str, str] | None = None,
        **kwargs,
    ) -> str:
        """导出 ICD 文件 (IEC 61850 SCL 标准格式)

        Args:
            model: IedModel 不可变模型
            output_path: 输出文件路径
            ied_name: IED 名称（自动推断时可选）
            pretty: 是否格式化 XML
            do_descriptions: DO 级别的 dU 描述值映射 {DO_ref → description}
        """
        self._do_descriptions = do_descriptions or {}
        if not ied_name:
            # 优先使用 IedModel 上保存的 ied_name
            ied_name = getattr(model, "ied_name", None) or ""
        if not ied_name:
            ied_name = self._infer_ied_name(model)

        scl_dict = self._model_to_scl_dict(model, ied_name)
        self._validate_scl_references(scl_dict)
        xml_str = xmltodict.unparse(scl_dict, pretty=pretty, indent="\t")
        # xmltodict 不自持自闭合标签，将空元素 <tag></tag> 转为 <tag/>
        xml_str = _RE_EMPTY_ELEMENT.sub(r"<\1\2/>", xml_str)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xml_str)
        return output_path

    @staticmethod
    def _as_list(value: Any) -> list[Any]:
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    @classmethod
    def _validate_scl_references(cls, scl_dict: dict[str, Any]) -> None:
        """Reject an ICD whose report/data-set references cannot resolve.

        The XML schema cannot detect an FCDA that names a missing DO/DA/BDA.
        Such a file can be parsed successfully while reports using that data
        set fail later. Validate the generated object graph before writing it.
        """

        scl = scl_dict.get("SCL", {})
        templates = scl.get("DataTypeTemplates", {})
        lnode_types = {item.get("@id", ""): item for item in cls._as_list(templates.get("LNodeType"))}
        do_types = {item.get("@id", ""): item for item in cls._as_list(templates.get("DOType"))}
        da_types = {item.get("@id", ""): item for item in cls._as_list(templates.get("DAType"))}

        ied = scl.get("IED", {})
        server = ied.get("AccessPoint", {}).get("Server", {})
        ldevices = cls._as_list(server.get("LDevice"))
        ld_by_inst = {ld.get("@inst", ""): ld for ld in ldevices}
        issues: list[str] = []

        def named_child(parent: dict[str, Any] | None, tag: str, name: str) -> dict[str, Any] | None:
            if not parent:
                return None
            return next((item for item in cls._as_list(parent.get(tag)) if item.get("@name") == name), None)

        def nodes_for(ld: dict[str, Any]) -> list[dict[str, Any]]:
            return cls._as_list(ld.get("LN0")) + cls._as_list(ld.get("LN"))

        for owner_ld in ldevices:
            for owner_ln in nodes_for(owner_ld):
                data_sets = cls._as_list(owner_ln.get("DataSet"))
                data_set_names = {item.get("@name", "") for item in data_sets}

                for report in cls._as_list(owner_ln.get("ReportControl")):
                    dat_set = report.get("@datSet", "")
                    if dat_set and dat_set not in data_set_names:
                        issues.append(f"ReportControl {report.get('@name', '')} -> missing DataSet {dat_set}")

                for gse_control in cls._as_list(owner_ln.get("GSEControl")):
                    dat_set = gse_control.get("@datSet", "")
                    if dat_set and dat_set not in data_set_names:
                        issues.append(f"GSEControl {gse_control.get('@name', '')} -> missing DataSet {dat_set}")

                for data_set in data_sets:
                    ds_name = data_set.get("@name", "")
                    for fcda in cls._as_list(data_set.get("FCDA")):
                        target_ld = ld_by_inst.get(fcda.get("@ldInst", ""))
                        if target_ld is None:
                            issues.append(f"DataSet {ds_name}: missing LDevice {fcda.get('@ldInst', '')}")
                            continue

                        target_ln = next(
                            (
                                node
                                for node in nodes_for(target_ld)
                                if node.get("@lnClass", "") == fcda.get("@lnClass", "")
                                and node.get("@inst", "") == fcda.get("@lnInst", "")
                                and node.get("@prefix", "") == fcda.get("@prefix", "")
                            ),
                            None,
                        )
                        ref_label = (
                            f"{fcda.get('@ldInst', '')}/{fcda.get('@prefix', '')}"
                            f"{fcda.get('@lnClass', '')}{fcda.get('@lnInst', '')}."
                            f"{fcda.get('@doName', '')}"
                        )
                        if target_ln is None:
                            issues.append(f"DataSet {ds_name}: missing LN for {ref_label}")
                            continue

                        lnode_type = lnode_types.get(target_ln.get("@lnType", ""))
                        do_entry = named_child(lnode_type, "DO", fcda.get("@doName", ""))
                        if do_entry is None:
                            issues.append(f"DataSet {ds_name}: missing DO {ref_label}")
                            continue

                        da_path = fcda.get("@daName", "")
                        if not da_path:
                            continue
                        parts = da_path.split(".")
                        do_type = do_types.get(do_entry.get("@type", ""))
                        da_entry = named_child(do_type, "DA", parts[0])
                        if da_entry is None:
                            issues.append(f"DataSet {ds_name}: missing DA {ref_label}.{da_path}")
                            continue

                        current = da_entry
                        missing_bda = False
                        for part in parts[1:]:
                            da_type = da_types.get(current.get("@type", ""))
                            current = named_child(da_type, "BDA", part)
                            if current is None:
                                issues.append(f"DataSet {ds_name}: missing BDA {ref_label}.{da_path}")
                                missing_bda = True
                                break
                        if missing_bda:
                            continue

                        fcda_fc = fcda.get("@fc", "")
                        template_fc = da_entry.get("@fc", "")
                        if fcda_fc != template_fc:
                            issues.append(
                                f"DataSet {ds_name}: FC mismatch {ref_label}.{da_path} ({fcda_fc} != {template_fc})"
                            )

        if issues:
            preview = "; ".join(issues[:10])
            if len(issues) > 10:
                preview += f"; ... total {len(issues)} issues"
            raise ValueError(f"ICD reference validation failed: {preview}")

    def export_xml(
        self,
        model: IedModel,
        output_path: str,
        *,
        pretty: bool = True,
        **kwargs,
    ) -> str:
        """导出自定义 XML 格式 (非标准 SCL 格式)"""
        xml_dict = self._model_to_xml_dict(model)
        xml_str = xmltodict.unparse(xml_dict, pretty=pretty, indent="  ")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xml_str)
        return output_path

    # ========== SCL/ICD 序列化 ==========

    _CDC_BTYPE_MAP = {
        "MV": {"mag": ("Struct", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        "CMV": {"cVal": ("Struct", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        "SAV": {"instMag": ("Struct", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        "SPS": {"stVal": ("BOOLEAN", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        "DPS": {"stVal": ("Dbpos", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        "INS": {"stVal": ("INT32", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        "ENS": {"stVal": ("Enum", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        "ACT": {"general": ("BOOLEAN", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        "ACD": {"general": ("BOOLEAN", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        "SEC": {"Cnt": ("INT32", None), "q": ("Quality", None), "t": ("Timestamp", None)},
        "SPC": {
            "stVal": ("BOOLEAN", None),
            "ctlVal": ("BOOLEAN", None),
            "Oper": ("Struct", None),
            "q": ("Quality", None),
            "t": ("Timestamp", None),
            "ctlModel": ("Enum", "ctlModel"),
        },
        "DPC": {
            "stVal": ("Dbpos", None),
            "ctlVal": ("Dbpos", None),
            "Oper": ("Struct", None),
            "q": ("Quality", None),
            "t": ("Timestamp", None),
            "ctlModel": ("Enum", "ctlModel"),
        },
        "ENC": {
            "stVal": ("Enum", None),
            "ctlVal": ("Enum", None),
            "Oper": ("Struct", None),
            "q": ("Quality", None),
            "t": ("Timestamp", None),
            "ctlModel": ("Enum", "ctlModel"),
        },
        "INC": {
            "stVal": ("INT32", None),
            "Oper": ("Struct", None),
            "q": ("Quality", None),
            "t": ("Timestamp", None),
            "ctlModel": ("Enum", "ctlModel"),
        },
        "APC": {
            "setVal": ("FLOAT32", None),
            "Oper": ("Struct", None),
            "q": ("Quality", None),
            "t": ("Timestamp", None),
            "ctlModel": ("Enum", "ctlModel"),
        },
        "ASG": {
            "setMag": ("Struct", None),
            "setVal": ("FLOAT32", None),
            "q": ("Quality", None),
            "t": ("Timestamp", None),
        },
        "LPL": {"vendor": ("VisString255", None), "swRev": ("VisString255", None), "d": ("VisString255", None)},
        "DPL": {"vendor": ("VisString255", None), "swRev": ("VisString255", None), "d": ("VisString255", None)},
    }

    _IEC_TYPE_TO_BTYPE = {
        IecType.FLOAT: "FLOAT32",
        IecType.BOOLEAN: "BOOLEAN",
        IecType.INTEGER: "INT32",
        IecType.UNKNOWN: "INT32",
        IecType.STRING: "VisString255",
        IecType.TIMESTAMP: "Timestamp",
    }

    # 已知结构体 DA 的默认子属性 — 在线发现未展开 sub_das 时使用
    _STRUCT_DA_DEFAULT_BDAS: dict[str, list[tuple[str, str]]] = {
        "mag": [("f", "FLOAT32"), ("i", "INT32")],
        "setMag": [("f", "FLOAT32"), ("i", "INT32")],
        "instMag": [("f", "FLOAT32"), ("i", "INT32")],
        "origin": [("orCat", "Enum"), ("orIdent", "Octet64")],
    }

    _BDA_ENUM_TYPE_MAP = {"orCat": "orCategory"}

    _DA_NAME_FC_MAP = {
        "mag": "MX",
        "cVal": "MX",
        "instMag": "MX",
        "mxVal": "MX",
        "fCVal": "MX",
        "setMag": "SP",
        "setVal": "SP",
        "wVal": "SP",
        "stVal": "ST",
        "general": "ST",
        "Cnt": "ST",
        "frVal": "ST",
        "frTm": "ST",
        "actVal": "ST",
        "subVal": "SV",
        "subEna": "SV",
        "ctlVal": "CO",
        "Oper": "CO",
        "SBO": "CO",
        "SBOw": "CO",
        "Cancel": "CO",
        "origin": "OR",
        "ctlNum": "CO",
        "AddCause": "CO",
        "valWTr": "CO",
        "q": "MX",
        "t": "MX",
        "blkEna": "BL",
        "dU": "DC",
        "du": "DC",
        "vendor": "DC",
        "swRev": "DC",
        "configRev": "DC",
        "d": "DC",
        "lnNs": "DC",
        "ldNs": "DC",
        "phNs": "DC",
        "cdcNs": "DC",
        "dataNs": "DC",
        "hwRev": "DC",
        "serNum": "DC",
        "model": "DC",
        "location": "DC",
        "ctlModel": "CF",
        "dbRef": "CF",
        "pulseConfig": "CF",
        "minVal": "CF",
        "maxVal": "CF",
        "stepSize": "CF",
        "units": "CF",
        "db": "CF",
        "zeroDb": "CF",
        "sVC": "CF",
        "rangeC": "CF",
        "smpRate": "CF",
        "subMag": "MX",
        "subQ": "SV",
        "subID": "SV",
    }

    _CDC_DEFAULT_FC_MAP = {
        "MV": "CF",
        "CMV": "CF",
        "SAV": "CF",
        "SPC": "CF",
        "DPC": "CF",
        "INC": "CF",
        "ENC": "CF",
        "APC": "CF",
        "ASG": "SP",
        "LPL": "DC",
        "DPL": "DC",
        "SPS": "ST",
        "DPS": "ST",
        "INS": "ST",
        "ENS": "ST",
        "ACT": "ST",
        "ACD": "ST",
        "SEC": "ST",
    }

    _CDC_QT_FC_MAP = {
        "MV": "MX",
        "CMV": "MX",
        "SAV": "MX",
        "APC": "MX",
        "SPS": "ST",
        "DPS": "ST",
        "INS": "ST",
        "ENS": "ST",
        "ACT": "ST",
        "ACD": "ST",
        "SEC": "ST",
        "SPC": "ST",
        "DPC": "ST",
        "INC": "ST",
        "ENC": "ST",
    }

    def _model_to_scl_dict(self, model: IedModel, ied_name: str) -> dict[str, Any]:
        type_templates = self._build_data_type_templates(model, ied_name)
        ied = self._build_ied_section(model, ied_name, type_templates)
        connected_ap: dict[str, Any] = {
            "@iedName": ied_name,
            "@apName": "S1",
            "Address": {
                "P": [
                    {"@type": "IP", "#text": model.host},
                    {"@type": "OSI-TSEL", "#text": "0001"},
                    {"@type": "OSI-SSEL", "#text": "0001"},
                    {"@type": "OSI-PSEL", "#text": "00000001"},
                ]
            },
        }
        gse_addresses = self._build_gse_addresses(model, ied_name)
        if gse_addresses:
            connected_ap["GSE"] = gse_addresses
        communication = {
            "SubNetwork": {
                "@name": "MMS",
                "@type": "8-MMS",
                "ConnectedAP": connected_ap,
            }
        }
        return {
            "SCL": {
                "@xmlns": "http://www.iec.ch/61850/2003/SCL",
                "Header": {
                    "@id": "",
                    "@version": "1",
                    "@revision": "",
                    "@toolID": "IEC61850ModelExporter",
                },
                "Communication": communication,
                "IED": ied,
                "DataTypeTemplates": type_templates,
            }
        }

    def _build_ied_section(self, model: IedModel, ied_name: str, type_templates: dict[str, Any]) -> dict[str, Any]:
        ldevice_list = []
        for ld in model.lds:
            ld_inst = self._get_ld_inst(ld, ied_name)
            ln0_item = None
            ln_list = []
            for ln in ld.lns:
                ln_type_id = self._build_ln_type_id(ied_name, ld_inst, ln.name)
                # 使用去重后的LNodeType id（如果存在映射）
                dedup_ln_type_id = self._ln_type_mapping.get(ln_type_id, ln_type_id)
                ln_inst = self._extract_ln_inst(ln.name)
                ln_class = ln.ln_class or self._extract_ln_class_from_name(ln.name)
                ln_prefix = self._extract_ln_prefix(ln.name, ln_class)
                if ln_class == "LLN0":
                    # GSEControl 也归属于 LLN0；仅含 GOOSE 控制块的 LLN0 仍须导出。
                    if not ln.dos and not ln.datasets and not ln.rcb_list and not ln.gocb_list:
                        continue
                    ln0_item = {
                        "@lnType": dedup_ln_type_id,
                        "@lnClass": "LLN0",
                        "@inst": "",
                    }
                    if ln.datasets:
                        ln0_item["DataSet"] = self._build_datasets(ln.datasets, ld_inst, ln, ld.lns)
                    if ln.rcb_list:
                        ln0_item["ReportControl"] = self._build_report_controls(ln.rcb_list)
                    if ln.gocb_list:
                        ln0_item["GSEControl"] = self._build_gse_controls(ln.gocb_list)
                else:
                    ln_item = {
                        "@lnType": dedup_ln_type_id,
                        "@lnClass": ln_class,
                        "@inst": ln_inst,
                    }
                    if ln_prefix:
                        ln_item["@prefix"] = ln_prefix
                    doi_list = self._build_dois(ln)
                    if doi_list:
                        ln_item["DOI"] = doi_list
                    if ln.datasets:
                        ln_item["DataSet"] = self._build_datasets(ln.datasets, ld_inst, ln, ld.lns)
                    if ln.rcb_list:
                        ln_item["ReportControl"] = self._build_report_controls(ln.rcb_list)
                    ln_list.append(ln_item)
            ldevice = {"@inst": ld_inst}
            if ln0_item:
                ldevice["LN0"] = ln0_item
            if ln_list:
                ldevice["LN"] = ln_list if len(ln_list) > 1 else ln_list[0]
            ldevice_list.append(ldevice)
        server = {"Authentication": {"@none": "true"}}
        if ldevice_list:
            server["LDevice"] = ldevice_list if len(ldevice_list) > 1 else ldevice_list[0]
        services = {
            "DynAssociation": None,
            "GetDirectory": None,
            "GetDataObjectDefinition": None,
            "DataObjectDirectory": None,
            "GetDataSetValue": None,
            "SetDataSetValue": None,
            "DataSetDirectory": None,
            "ReadWrite": None,
            "ConfReportControl": {"@max": str(sum(len(ln.rcb_list) for ld in model.lds for ln in ld.lns))},
            "GetCBValues": None,
        }
        goose_count = sum(len(ln.gocb_list) for ld in model.lds for ln in ld.lns)
        if goose_count:
            services["GOOSE"] = {"@max": str(goose_count)}
        services["ConfLNs"] = {"@fixPrefix": "true", "@fixLnInst": "true"}

        return {
            "@name": ied_name,
            "Services": services,
            "AccessPoint": {
                "@name": "S1",
                "Server": server,
            },
        }

    def _build_data_type_templates(self, model: IedModel, ied_name: str) -> dict[str, Any]:
        _reset_type_counters()
        lnode_types = []
        do_types = []
        da_types = []
        enum_types: dict[str, list[dict[str, str]]] = {}

        # 标准 CTL 枚举
        self._init_enum_types(enum_types)

        do_type_cache: dict[tuple, str] = {}  # (cdc, da_fingerprint) → do_type_id
        da_type_cache: dict[tuple, str] = {}  # bda_fingerprint → da_type_id
        # LNodeType去重映射: fingerprint → lnode_type_id
        lnode_fingerprint_cache: dict[tuple, str] = {}
        # 原始ln_type_id → 去重后ln_type_id 的映射
        self._ln_type_mapping: dict[str, str] = {}

        for ld in model.lds:
            ld_inst = self._get_ld_inst(ld, ied_name)
            for ln in ld.lns:
                ln_type_id = self._build_ln_type_id(ied_name, ld_inst, ln.name)
                ln_class = ln.ln_class or self._extract_ln_class_from_name(ln.name)
                do_refs = []

                for do in ln.dos:
                    # 在线发现得到的 CDC 优先；仅在缺失时才按 LN/DO 名称推断。
                    # 这对厂商自定义 LN（如 CTRL 下的 ASG.setMag）尤其重要。
                    cdc = do.cdc or self._infer_cdc_from_do(do.name, ln_class)
                    do_type_id = self._resolve_or_create_do_type(
                        do,
                        cdc,
                        ln_type_id,
                        do_type_cache,
                        da_type_cache,
                        do_types,
                        da_types,
                        enum_types,
                    )
                    do_refs.append({"@name": do.name, "@type": do_type_id})

                # 资源型 LLN0（DataSet/RCB/GoCB）仍会被 IED 段引用，保留其 LNodeType。
                if not do_refs and ln_class == "LLN0" and not ln.datasets and not ln.rcb_list and not ln.gocb_list:
                    continue

                # LNodeType去重：对具有相同lnClass和DO结构（名称+类型）的LNodeType进行合并
                do_fingerprint = tuple(sorted((ref["@name"], ref["@type"]) for ref in do_refs))
                ln_fingerprint = (ln_class, do_fingerprint)
                if ln_fingerprint in lnode_fingerprint_cache:
                    # 命中缓存，使用已存在的LNodeType id
                    dedup_id = lnode_fingerprint_cache[ln_fingerprint]
                    self._ln_type_mapping[ln_type_id] = dedup_id
                else:
                    lnode_fingerprint_cache[ln_fingerprint] = ln_type_id
                    lnode_type = {"@id": ln_type_id, "@lnClass": ln_class}
                    if do_refs:
                        lnode_type["DO"] = do_refs if len(do_refs) > 1 else do_refs[0]
                    lnode_types.append(lnode_type)

        return self._assemble_type_templates(lnode_types, do_types, da_types, enum_types)

    def _init_enum_types(self, enum_types: dict[str, list[dict[str, str]]]) -> None:
        enum_types["ctlModel"] = [
            {"@ord": str(i), "#text": v}
            for i, v in enumerate(
                [
                    "status-only",
                    "direct-with-normal-security",
                    "sbo-with-normal-security",
                    "direct-with-enhanced-security",
                    "sbo-with-enhanced-security",
                ]
            )
        ]
        enum_types["orCategory"] = [
            {"@ord": str(i), "#text": v}
            for i, v in enumerate(
                [
                    "not-supported",
                    "bay-control",
                    "station-control",
                    "remote-control",
                    "automatic-bay",
                    "automatic-station",
                    "automatic-remote",
                    "maintenance",
                    "process",
                ]
            )
        ]
        enum_types["BehKind"] = [
            {"@ord": "1", "#text": "on"},
            {"@ord": "2", "#text": "blocked"},
            {"@ord": "3", "#text": "test"},
            {"@ord": "4", "#text": "test/blocked"},
            {"@ord": "5", "#text": "off"},
        ]
        enum_types["HealthKind"] = [
            {"@ord": "1", "#text": "OK"},
            {"@ord": "2", "#text": "Warning"},
            {"@ord": "3", "#text": "Alarm"},
        ]

    def _make_do_type_fingerprint(self, do, cdc: str) -> tuple:
        """生成 DOType 去重指纹: (cdc, sorted_da_tuples)

        对于 Struct 类型 DA，额外包含 BDA 指纹以区分不同的子结构。
        例如 mag.f 和 mag.i 应生成不同的 DOType 引用。
        """
        da_tuples = []
        for da in do.das:
            fc = self._resolve_fc(da, cdc)
            btype, type_ref = self._resolve_btype(da, do.name, cdc, "")
            # 对于 Struct 类型，加上 BDA 指纹以区分不同子属性组合
            bda_fp = self._make_da_type_fingerprint(da) if btype == "Struct" else ()
            enum_type_ref = type_ref if btype == "Enum" else ""
            da_tuples.append((da.name, fc, btype, enum_type_ref, bda_fp))
        da_tuples.sort(key=lambda x: x[0])
        return (cdc, tuple(da_tuples))

    def _resolve_or_create_do_type(
        self,
        do,
        cdc: str,
        ln_type_id: str,
        do_type_cache: dict,
        da_type_cache: dict,
        do_types: list,
        da_types: list,
        enum_types: dict,
    ) -> str:
        """查找或创建共享 DOType

        DOType 使用结构指纹全局去重，相同 CDC + DA 结构的 DO 共享同一 DOType，
        无论它们属于哪个 LN/LD。DOType ID 使用首次出现的 `{ln_type_id}.{do_name}` 格式，
        保持可读性。

        Returns:
            do_type_id: 共享的 DOType ID
        """
        fingerprint = self._make_do_type_fingerprint(do, cdc)
        # 全局缓存（不绑定 ln_type_id），使跨 LN 的相同结构 DO 共享 DOType
        if fingerprint in do_type_cache:
            return do_type_cache[fingerprint]

        do_type_id = f"{ln_type_id}.{do.name}"
        do_type_cache[fingerprint] = do_type_id

        do_type_item = {"@id": do_type_id, "@cdc": cdc}
        da_refs = []

        for da in do.das:
            fc = self._resolve_fc(da, cdc)
            btype, da_type_ref = self._resolve_btype(da, do.name, cdc, ln_type_id)
            da_ref = {"@name": da.name, "@fc": fc, "@bType": btype}
            if da_type_ref:
                da_ref["@type"] = da_type_ref
            if btype == "Enum" and da_type_ref and da_type_ref not in enum_types:
                enum_types[da_type_ref] = [{"@ord": "0", "#text": "unknown"}]
            da_refs.append(da_ref)

            # 创建 DAType (struct DA 的子属性)
            # 优先级: 在线发现的 sub_das > 默认 BDA 定义
            # 在线发现反映了 IED 实际支持的子属性。
            # 例如：Temp001.mag.f（浮点测量值）vs SglMaxVolNo.mag.i（整型状态值），
            # 两者的 mag 应有不同的 DAType 定义。
            # 默认定义为兜底（在线发现失败时使用）。
            if btype == "Struct" and da.sub_das:
                da_type_id = self._resolve_or_create_da_type(da, da_type_cache, da_types)
                da_ref["@type"] = da_type_id
            elif btype == "Struct" and da.name in self._STRUCT_DA_DEFAULT_BDAS:
                da_type_id = self._resolve_or_create_default_da_type(da, da_type_cache, da_types)
                da_ref["@type"] = da_type_id

        if da_refs:
            do_type_item["DA"] = da_refs if len(da_refs) > 1 else da_refs[0]
        do_types.append(do_type_item)
        return do_type_id

    def _make_da_type_fingerprint(self, da) -> tuple:
        """生成 DAType 去重指纹

        优先级: 在线发现的 sub_das > 默认 BDA 定义
        在线发现反映了 IED 实际支持的子属性（如 mag.f 或 mag.i），
        默认定义为兜底方案（在线发现失败时使用）。
        """
        if da.sub_das:
            return tuple(sorted(self._make_bda_fingerprint(bda) for bda in da.sub_das))
        if da.name in self._STRUCT_DA_DEFAULT_BDAS:
            return tuple(
                sorted(
                    (name, btype, self._BDA_ENUM_TYPE_MAP.get(name, ""))
                    for name, btype in self._STRUCT_DA_DEFAULT_BDAS[da.name]
                )
            )
        return ()

    def _make_bda_fingerprint(self, bda) -> tuple:
        if bda.sub_das:
            nested = tuple(sorted(self._make_bda_fingerprint(child) for child in bda.sub_das))
            return (bda.name, "Struct", "", nested)
        if bda.name in self._STRUCT_DA_DEFAULT_BDAS:
            nested = tuple(
                sorted(
                    (name, btype, self._BDA_ENUM_TYPE_MAP.get(name, ""))
                    for name, btype in self._STRUCT_DA_DEFAULT_BDAS[bda.name]
                )
            )
            return (bda.name, "Struct", "", nested)
        enum_type = self._BDA_ENUM_TYPE_MAP.get(bda.name, "")
        btype = "Enum" if enum_type else self._IEC_TYPE_TO_BTYPE.get(bda.iec_type, "INT32")
        return (bda.name, btype, enum_type, ())

    def _resolve_or_create_da_type(
        self,
        da,
        da_type_cache: dict,
        da_types: list,
    ) -> str:
        """查找或创建共享 DAType"""
        fingerprint = self._make_da_type_fingerprint(da)
        if fingerprint in da_type_cache:
            return da_type_cache[fingerprint]

        da_type_id = _next_da_type_id(da.name.upper())
        da_type_cache[fingerprint] = da_type_id

        bda_refs = []
        for bda in da.sub_das:
            if bda.sub_das:
                bda_ref = {
                    "@name": bda.name,
                    "@bType": "Struct",
                    "@type": self._resolve_or_create_da_type(bda, da_type_cache, da_types),
                }
            elif bda.name in self._STRUCT_DA_DEFAULT_BDAS:
                bda_ref = {
                    "@name": bda.name,
                    "@bType": "Struct",
                    "@type": self._resolve_or_create_default_da_type(bda, da_type_cache, da_types),
                }
            else:
                enum_type = self._BDA_ENUM_TYPE_MAP.get(bda.name)
                bda_btype = "Enum" if enum_type else self._IEC_TYPE_TO_BTYPE.get(bda.iec_type, "INT32")
                bda_ref = {"@name": bda.name, "@bType": bda_btype}
                if enum_type:
                    bda_ref["@type"] = enum_type
            bda_refs.append(bda_ref)

        da_type_item = {"@id": da_type_id}
        da_type_item["BDA"] = bda_refs if len(bda_refs) > 1 else bda_refs[0]
        da_types.append(da_type_item)
        return da_type_id

    def _resolve_or_create_default_da_type(
        self,
        da,
        da_type_cache: dict,
        da_types: list,
    ) -> str:
        """查找或创建使用默认 BDA 的 DAType"""
        fingerprint = self._make_da_type_fingerprint(da)
        if fingerprint in da_type_cache:
            return da_type_cache[fingerprint]

        da_type_id = _next_da_type_id(da.name.upper())
        da_type_cache[fingerprint] = da_type_id

        bda_refs = []
        for bda_name, bda_btype in self._STRUCT_DA_DEFAULT_BDAS[da.name]:
            bda_ref = {"@name": bda_name, "@bType": bda_btype}
            enum_type = self._BDA_ENUM_TYPE_MAP.get(bda_name)
            if enum_type:
                bda_ref["@type"] = enum_type
            bda_refs.append(bda_ref)

        da_type_item = {"@id": da_type_id}
        da_type_item["BDA"] = bda_refs if len(bda_refs) > 1 else bda_refs[0]
        da_types.append(da_type_item)
        return da_type_id

    @staticmethod
    def _assemble_type_templates(
        lnode_types: list,
        do_types: list,
        da_types: list,
        enum_types: dict[str, list[dict[str, str]]],
    ) -> dict[str, Any]:
        """组装最终的类型模板字典"""
        result = {}
        if lnode_types:
            result["LNodeType"] = lnode_types if len(lnode_types) > 1 else lnode_types[0]
        if do_types:
            result["DOType"] = do_types if len(do_types) > 1 else do_types[0]
        if da_types:
            result["DAType"] = da_types if len(da_types) > 1 else da_types[0]
        enum_list = []
        for enum_id, vals in enum_types.items():
            enum_item = {"@id": enum_id}
            enum_item["EnumVal"] = vals if len(vals) > 1 else vals[0]
            enum_list.append(enum_item)
        if enum_list:
            result["EnumType"] = enum_list if len(enum_list) > 1 else enum_list[0]
        return result

    def _build_dois(self, ln) -> list[dict[str, Any]]:
        """Build instance overrides for values known by the client.

        The discovered ``DARef`` objects describe the data *type*.  Merely
        discovering a DA does not mean that an ICD needs a corresponding
        empty DAI/SDI in the instance section; the DOType/DAType templates
        already carry that structure.  At present the client retains only
        the dU description value, so that is the only instance override that
        can be exported faithfully.
        """
        doi_list = []
        for do in ln.dos:
            do_descriptions = getattr(self, "_do_descriptions", {})
            du_val = do_descriptions.get(do.ref, "") if do_descriptions else ""
            du_da = next((da for da in do.das if da.name in ("dU", "du")), None)
            if du_val and du_da is not None:
                doi_list.append(
                    {
                        "@name": do.name,
                        "DAI": {"@name": du_da.name, "Val": du_val},
                    }
                )
        return doi_list if len(doi_list) > 1 else (doi_list[0] if doi_list else [])

    def _build_datasets(self, datasets, ld_inst: str, ln, discovered_lns) -> Any:
        # 构建 LN 索引: (lnClass, lnInst) → discovered LN
        # 同时构建所有 DO 名称集合用于灵活匹配
        ln_index: dict[tuple[str, str, str], Any] = {}
        all_do_names: set[str] = set()
        for dln in discovered_lns:
            dln_class = dln.ln_class or self._extract_ln_class_from_name(dln.name) or ""
            dln_inst = self._extract_ln_inst(dln.name)
            dln_prefix = self._extract_ln_prefix(dln.name, dln_class)
            ln_index[(dln_prefix, dln_class, dln_inst)] = dln
            for do in dln.dos:
                all_do_names.add(do.name)

        ds_list = []
        for ds in datasets:
            ds_item = {"@name": ds.name}
            fcda_list = []
            for m in ds.members:
                ref = m.get("ref", "")
                fcda = {
                    "@ldInst": ld_inst,
                    "@fc": m.get("fc", ""),
                }
                if ref and "/" in ref:
                    after_slash = ref.split("/", 1)[1]
                    dot_parts = after_slash.split(".")
                    if len(dot_parts) >= 2:
                        ref_ln = dot_parts[0]
                        fcda["@doName"] = dot_parts[1]
                        fcda["@lnClass"] = self._extract_ln_class_from_name(ref_ln) or ""
                        fcda["@lnInst"] = self._extract_ln_inst(ref_ln)
                        prefix = self._extract_ln_prefix(ref_ln, fcda["@lnClass"])
                        if prefix:
                            fcda["@prefix"] = prefix
                        if len(dot_parts) > 2:
                            fcda["@daName"] = ".".join(dot_parts[2:])
                else:
                    fcda["@lnClass"] = ln.ln_class or ""
                    fcda["@lnInst"] = self._extract_ln_inst(ln.name)
                    fcda["@doName"] = m.get("doName", "")
                    if m.get("da"):
                        fcda["@daName"] = m["da"]
                    elif ref and "." in ref:
                        parts = ref.split(".")
                        if len(parts) >= 3:
                            fcda["@doName"] = parts[-3]
                            fcda["@daName"] = ".".join(parts[2:])
                        else:
                            fcda["@doName"] = parts[0]

                # FCDA 匹配检查:
                # 1. 优先通过 LN 名称匹配（类名+实例号 或 原始名）
                # 2. 如果 LN 名不匹配，通过 DO 名称匹配（MMS DataSet 的 LN 名
                #    可能是短格式如 "L1" 而非 "MMCL1"，但 DO 名始终准确）
                fcda_do_name = fcda.get("@doName", "")
                matched_ln = self._find_ln_for_fcda(fcda, ln_index, discovered_lns)
                if matched_ln is not None:
                    self._normalize_fcda_ln(fcda, matched_ln)
                    self._normalize_fcda_fc(fcda, matched_ln)
                elif fcda_do_name in all_do_names:
                    # 通过 DO 名称匹配到模型：查找拥有该 DO 的 LN
                    matched_ln = self._find_ln_by_do_name(discovered_lns, fcda_do_name)
                    if matched_ln is not None:
                        # Update FCDA lnClass/lnInst from the discovered LN.
                        self._normalize_fcda_ln(fcda, matched_ln)
                        self._normalize_fcda_fc(fcda, matched_ln)
                    else:
                        # DO 名匹配也失败，跳过此 FCDA
                        continue
                else:
                    continue
                # 验证FCDA的必要属性不为空，避免输出冗余空标签
                if fcda.get("@lnClass") and fcda.get("@doName"):
                    fcda_list.append(fcda)

            # 过滤FCDA列表：移除所有不完整的FCDA条目
            valid_fcda = []
            for fcda in fcda_list:
                if fcda.get("@lnClass") and fcda.get("@doName") and fcda.get("@fc"):
                    valid_fcda.append(fcda)

            if valid_fcda:
                ds_item["FCDA"] = valid_fcda if len(valid_fcda) > 1 else valid_fcda[0]
                ds_list.append(ds_item)
        return ds_list if len(ds_list) > 1 else (ds_list[0] if ds_list else [])

    def _find_ln_for_fcda(self, fcda: dict[str, Any], ln_index: dict[tuple[str, str, str], Any], discovered_lns):
        do_name = fcda.get("@doName", "")
        key = (
            fcda.get("@prefix", ""),
            fcda.get("@lnClass", ""),
            fcda.get("@lnInst", ""),
        )
        matched_ln = ln_index.get(key)
        if matched_ln is not None and self._ln_has_do(matched_ln, do_name):
            return matched_ln
        return self._find_ln_by_do_name(discovered_lns, do_name)

    @staticmethod
    def _find_ln_by_do_name(discovered_lns, do_name: str):
        """通过 DO 名称查找所属的逻辑节点"""
        for dln in discovered_lns:
            if IcdExporter._ln_has_do(dln, do_name):
                return dln
        return None

    @staticmethod
    def _ln_has_do(ln, do_name: str) -> bool:
        return any(do.name == do_name for do in ln.dos)

    def _normalize_fcda_fc(self, fcda: dict[str, Any], ln) -> None:
        do_name = fcda.get("@doName", "")
        if not do_name:
            return

        matched_do = next((do for do in ln.dos if do.name == do_name), None)
        if matched_do is None:
            return

        da_path = fcda.get("@daName", "")
        da_name = da_path.split(".", 1)[0]
        if da_name:
            for da in matched_do.das:
                if da.name == da_name or da.path == da_path:
                    if da.fc:
                        fcda["@fc"] = da.fc
                    return
            return

        for da in matched_do.das:
            if da.name not in ("q", "t", "dU", "du") and da.fc:
                fcda["@fc"] = da.fc
                return

    @staticmethod
    def _strip_report_name_suffix(name: str) -> str:
        """去除报告名尾部数字后缀，获取基础名。

        只剥离末尾2位数字后缀（如 "urcbAin01" → "urcbAin"），
        避免误伤报告名本身末尾的个位数字。
        若去除后缀后为空或名本身无数字后缀，返回原值。
        """
        stripped = re.sub(r"\d{2}$", "", name)
        return stripped if stripped else name

    def _build_report_controls(self, rcb_list) -> Any:
        """构建ReportControl XML元素。

        尾部带数字后缀的报告名视为同一报告的多实例，合并为一个ReportControl，
        RptEnabled的max属性记录实例数量。

        例如: urcbAin01~urcbAin12 12个实例 → 1个ReportControl + RptEnabled max="12"
        """
        # 按基础名聚合RCB，统计每个报告的实例数
        rcb_groups: dict[str, dict] = {}
        for rcb in rcb_list:
            base_name = self._strip_report_name_suffix(rcb.name)
            if base_name not in rcb_groups:
                buffered = "true" if rcb.rcb_type == "BRCB" else "false"
                item = {
                    "@name": base_name,
                    "@rptID": base_name,
                    "@buffered": buffered,
                    "@bufTime": "0",
                    "@confRev": "1",
                }
                # 如果有datSet引用，则加入ReportControl的属性中
                if rcb.dat_set:
                    item["@datSet"] = rcb.dat_set
                # 如果有intgPd(完整性周期)，则加入ReportControl的属性中(仅URCB)
                if rcb.intg_pd:
                    item["@intgPd"] = str(rcb.intg_pd)
                item["TrgOps"] = {
                    "@dchg": "true" if rcb.trg_ops & 0x01 else "false",
                    "@qchg": "true" if rcb.trg_ops & 0x02 else "false",
                    "@dupd": "true" if rcb.trg_ops & 0x04 else "false",
                    "@period": "true" if rcb.trg_ops & 0x08 else "false",
                    "@gi": "true" if rcb.trg_ops & 0x10 else "false",
                }
                item["OptFields"] = {
                    "@seqNum": "true" if rcb.opt_fields & 0x01 else "false",
                    "@timeStamp": "true" if rcb.opt_fields & 0x02 else "false",
                    "@reasonCode": "true" if rcb.opt_fields & 0x04 else "false",
                    "@dataSet": "true" if rcb.opt_fields & 0x08 else "false",
                    "@dataRef": "true" if rcb.opt_fields & 0x10 else "false",
                    "@bufOvfl": "true" if rcb.opt_fields & 0x20 else "false",
                    "@entryID": "true" if rcb.opt_fields & 0x40 else "false",
                    "@configRef": "true" if rcb.opt_fields & 0x80 else "false",
                }
                item["RptEnabled"] = {"@max": "1"}
                item["_count"] = 1
                rcb_groups[base_name] = item
            else:
                rcb_groups[base_name]["_count"] += 1

        rcb_items = []
        for item in rcb_groups.values():
            count = item.pop("_count", 1)
            item["RptEnabled"]["@max"] = str(count)
            rcb_items.append(item)

        return rcb_items if len(rcb_items) > 1 else (rcb_items[0] if rcb_items else [])

    @staticmethod
    def _dataset_name_from_ref(data_set_ref: str) -> str:
        """Convert an MMS DataSet object reference to the local SCL name."""
        if not data_set_ref:
            return ""
        local_ref = data_set_ref.rsplit("/", 1)[-1]
        if "$" in local_ref:
            return local_ref.rsplit("$", 1)[-1]
        if "." in local_ref:
            return local_ref.rsplit(".", 1)[-1]
        return local_ref

    def _build_gse_controls(self, gocb_list) -> Any:
        """Build SCL ``GSEControl`` elements from discovered GoCB metadata."""
        items = []
        for gocb in gocb_list:
            item = {
                "@name": gocb.name,
                "@type": "GOOSE",
                "@confRev": str(gocb.conf_rev),
            }
            data_set_name = self._dataset_name_from_ref(gocb.data_set_ref)
            if data_set_name:
                item["@datSet"] = data_set_name
            if gocb.go_id:
                # The MMS GoID maps to SCL GSEControl.appID.  The numeric
                # destination APPID belongs to Communication/GSE/Address.
                item["@appID"] = gocb.go_id
            items.append(item)
        return items if len(items) > 1 else (items[0] if items else [])

    def _build_gse_addresses(self, model: IedModel, ied_name: str) -> Any:
        """Build Communication/GSE entries from transport data exposed over MMS."""
        items = []
        for ld in model.lds:
            ld_inst = self._get_ld_inst(ld, ied_name)
            for ln in ld.lns:
                for gocb in ln.gocb_list:
                    if gocb.app_id is None:
                        continue
                    items.append(
                        {
                            "@ldInst": ld_inst,
                            "@cbName": gocb.name,
                            "Address": {
                                "P": {
                                    "@type": "APPID",
                                    "#text": f"{int(gocb.app_id) & 0xFFFF:04X}",
                                }
                            },
                        }
                    )
        return items if len(items) > 1 else (items[0] if items else [])

    def _model_to_xml_dict(self, model: IedModel) -> dict[str, Any]:
        """转换为 xmltodict 兼容的自定义 XML 字典"""
        ld_list = []
        for ld in model.lds:
            ln_list = []
            for ln in ld.lns:
                ln_item = {"@name": ln.name, "@lnClass": ln.ln_class, "@ref": ln.ref}
                if ln.dos:
                    do_list = []
                    for do in ln.dos:
                        do_item = {
                            "@name": do.name,
                            "@ref": do.ref,
                            "@frameType": str(do.frame_type),
                            "@frameTypeDesc": FRAME_TYPE_DESC.get(do.frame_type, "未知"),
                        }
                        if do.das:
                            da_list = []
                            for da in do.das:
                                da_item = {"@name": da.name, "@path": da.path, "@fc": da.fc, "@iecType": da.iec_type}
                                if da.sub_das:
                                    bda_list = [
                                        {"@name": bda.name, "@path": bda.path, "@fc": bda.fc, "@iecType": bda.iec_type}
                                        for bda in da.sub_das
                                    ]
                                    da_item["SubDataAttributes"] = {
                                        "SubDataAttribute": bda_list if len(bda_list) > 1 else bda_list[0]
                                    }
                                da_list.append(da_item)
                            do_item["DataAttributes"] = {"DataAttribute": da_list if len(da_list) > 1 else da_list[0]}
                        do_list.append(do_item)
                    ln_item["DataObjects"] = {"DataObject": do_list if len(do_list) > 1 else do_list[0]}
                if ln.datasets:
                    ds_list = []
                    for ds in ln.datasets:
                        ds_item = {"@name": ds.name, "@ref": ds.ref, "@isDeletable": str(ds.is_deletable)}
                        if ds.members:
                            member_list = []
                            for m in ds.members:
                                member_item = {"@ref": m.get("ref", ""), "@fc": m.get("fc", "")}
                                if m.get("da"):
                                    member_item["@da"] = m["da"]
                                member_list.append(member_item)
                            ds_item["Members"] = {"Member": member_list if len(member_list) > 1 else member_list[0]}
                        ds_list.append(ds_item)
                    ln_item["DataSets"] = {"DataSet": ds_list if len(ds_list) > 1 else ds_list[0]}
                if ln.rcb_list:
                    rcb_list = [{"@name": rcb.name, "@ref": rcb.ref, "@type": rcb.rcb_type} for rcb in ln.rcb_list]
                    ln_item["ReportControlBlocks"] = {
                        "ReportControlBlock": rcb_list if len(rcb_list) > 1 else rcb_list[0]
                    }
                if ln.gocb_list:
                    gocb_list = [{"@name": gocb.name, "@ref": gocb.ref} for gocb in ln.gocb_list]
                    ln_item["GooseControlBlocks"] = {
                        "GooseControlBlock": gocb_list if len(gocb_list) > 1 else gocb_list[0]
                    }
                ln_list.append(ln_item)
            ld_item = {"@name": ld.name, "@inst": ld.inst}
            if ln_list:
                ld_item["LogicalNodes"] = {"LogicalNode": ln_list if len(ln_list) > 1 else ln_list[0]}
            ld_list.append(ld_item)

        summary = model.summary
        return {
            "ServerModel": {
                "@host": model.host,
                "@port": str(model.port),
                "@discoverTime": model.discover_time,
                "LogicalDevices": {"LogicalDevice": ld_list if len(ld_list) > 1 else ld_list[0]},
                "Summary": {
                    "@totalLDs": str(summary["totalLDs"]),
                    "@totalLNs": str(summary["totalLNs"]),
                    "@totalDOs": str(summary["totalDOs"]),
                    "@totalDAs": str(summary["totalDAs"]),
                    "@totalDataSets": str(summary["totalDataSets"]),
                    "@totalRCBs": str(summary["totalRCBs"]),
                    "@totalGoCBs": str(summary["totalGoCBs"]),
                },
            }
        }

    # ========== 辅助方法 ==========

    def _infer_ied_name(self, model: IedModel) -> str:
        ld_names = [ld.name for ld in model.lds if getattr(ld, "name", "")]
        if not ld_names:
            return "IED"

        # 策略1: 多LD时尝试公共前缀
        if len(ld_names) > 1:
            prefix = os.path.commonprefix(ld_names).rstrip("_-. ")
            if prefix:
                # 检查每个LD的剩余部分是否为合法的LD实例名
                rest_parts = [name[len(prefix) :].lstrip("_-. ") for name in ld_names]
                if all(self._looks_like_ld_inst(part) for part in rest_parts if part):
                    return prefix.rstrip("_-. ")
                if (
                    prefix[-1:].isdigit()
                    and all(part for part in rest_parts)
                    and all(self._looks_like_named_ld_inst(part) for part in rest_parts)
                ):
                    return prefix.rstrip("_-. ")

        # 策略2: 从第一个LD名中拆分已知后缀
        suffix_split = self._split_known_ld_suffix(ld_names[0])
        if suffix_split is not None:
            ied_name, _ = suffix_split
            return ied_name

        # 策略3: 从左分割下划线，IED名本身可能包含下划线时从左取
        parts = ld_names[0].split("_", 1)
        if len(parts) > 1 and parts[0]:
            return parts[0]

        # 策略4: 回退，整个LD名作为IED名
        return ld_names[0]

    def _get_ld_inst(self, ld, ied_name: str) -> str:
        ld_name = getattr(ld, "name", "") or ""
        ld_inst = getattr(ld, "inst", "") or ""
        if ld_inst and ld_inst != ld_name:
            return self._extract_ld_inst(ld_inst, ied_name)
        return self._extract_ld_inst(ld_name, ied_name)

    @staticmethod
    def _build_ln_type_id(ied_name: str, ld_inst: str, ln_name: str) -> str:
        """Build a stable LNodeType ID without duplicating the IED prefix."""
        if not ied_name:
            owner = ld_inst
        elif not ld_inst or ld_inst == ied_name:
            owner = ied_name
        elif ld_inst.startswith(ied_name):
            owner = ld_inst
        else:
            owner = f"{ied_name}{ld_inst}"
        return f"{owner}.{ln_name}" if owner else ln_name

    @staticmethod
    def _looks_like_ld_inst(value: str) -> bool:
        if not value:
            return False
        return bool(re.match(r"^(LD\d+|CTRL\d*|MEAS\d*|PROT\d*|CTMP\d*|BAY\d*|PIGO\d*|GOOSE\d*|MMS\d*)$", value))

    @staticmethod
    def _looks_like_named_ld_inst(value: str) -> bool:
        if not value:
            return False
        return bool(re.match(r"^(?=.*[A-Za-z]{2})[A-Za-z][A-Za-z0-9]*$", value))

    @staticmethod
    def _split_known_ld_suffix(ld_name: str) -> tuple[str, str] | None:
        """从LD名中拆分已知后缀。

        已知后缀包含标准LD实例名模式，拆分时确保IED名不包含尾部非字母数字字符。
        例如: "KG_BAMSCTMP01" → ("KG_BAMS", "CTMP01")
              "PCS001LD0" → ("PCS001", "LD0")
              "IED1_LD0" → ("IED1", "LD0")
        """
        match = re.match(
            r"^(.+?)(LD\d+|CTRL\d*|MEAS\d*|PROT\d*|CTMP\d*|BAY\d*|PIGO\d*|GOOSE\d*|MMS\d*)$",
            ld_name,
        )
        if not match:
            return None
        ied_name, ld_inst = match.groups()
        if not ied_name or not ld_inst:
            return None
        # 去除IED名尾部分隔符（下划线、连字符等）
        ied_name = ied_name.rstrip("_-. ")
        if not ied_name:
            return None
        return (ied_name, ld_inst)

    @staticmethod
    def _extract_ln_prefix(ln_name: str, ln_class: str) -> str:
        if not ln_name or not ln_class or ln_class == "LLN0":
            return ""
        idx = ln_name.find(ln_class)
        return ln_name[:idx] if idx > 0 else ""

    def _normalize_fcda_ln(self, fcda: dict[str, Any], ln) -> None:
        ln_class = ln.ln_class or self._extract_ln_class_from_name(ln.name) or ""
        fcda["@lnClass"] = ln_class
        fcda["@lnInst"] = self._extract_ln_inst(ln.name)
        prefix = self._extract_ln_prefix(ln.name, ln_class)
        if prefix:
            fcda["@prefix"] = prefix
        else:
            fcda.pop("@prefix", None)

    def _extract_ld_inst(self, ld_name: str, ied_name: str) -> str:
        if not ld_name:
            return ""
        if not ied_name:
            return ld_name
        if ld_name.startswith(ied_name + "_"):
            return ld_name[len(ied_name) + 1 :]
        if ld_name.startswith(ied_name):
            rest = ld_name[len(ied_name) :]
            if rest:
                return rest
        return ld_name

    def _extract_ln_inst(self, ln_name: str) -> str:
        if ln_name == "LLN0":
            return ""
        m = re.search(r"(\d+)$", ln_name)
        return m.group(1) if m else "1"

    def _extract_ln_class_from_name(self, ln_name: str) -> str:
        """从 LN 名称中提取逻辑节点类名

        规则:
        1. LLN0 → LLN0
        2. 匹配纯字母前缀作为类名（去除尾部数字）
        3. 无数字后缀时，返回完整字母部分
        """
        if ln_name == "LLN0":
            return "LLN0"
        # 匹配开头的字母序列 → 类名, 后续数字 → 实例号
        m = re.match(r"^([A-Za-z]+)(\d*)$", ln_name)
        if m:
            return m.group(1)
        # 回退: 移除尾部数字
        return re.sub(r"\d+$", "", ln_name)

    def _infer_cdc_from_do(self, do_name: str, ln_class: str) -> str:
        if do_name in ("Mod", "Beh", "Health"):
            return "ENC"
        if do_name == "NamPlt":
            return "LPL"
        if do_name == "DNamPlt":
            return "DPL"
        if ln_class in ("MMXU", "MMTR", "MMLN", "MSQI", "MHAN", "MSTA"):
            if do_name.startswith("PhV") or do_name.startswith("CV"):
                return "CMV"
            return "MV"
        if ln_class in ("GGIO", "CSWI", "XSWI"):
            if do_name.startswith("DPCSO") or do_name.startswith("SBO"):
                return "DPC"
            if do_name.startswith("SPCSO") or do_name.startswith("Ind"):
                return "SPC"
            if do_name.startswith("AnIn") or do_name.startswith("AnOut"):
                return "MV"
            if do_name.startswith("DInd") or do_name.startswith("BinIn"):
                return "SPS"
            return "SPS"
        if ln_class in ("PTOC", "PDIR", "PVOC", "PIOC", "PSDE"):
            return "ACT"
        if ln_class == "LLN0":
            if do_name == "NamPlt":
                return "LPL"
            return "SPS"
        if do_name.startswith("DInd"):
            return "DPS"
        if do_name.startswith(("Ind", "Alm", "St", "Blk", "Sw")):
            return "SPS"
        return "MV"

    def _resolve_fc(self, da, cdc: str) -> str:
        if da.name in ("q", "t"):
            qt_fc = self._CDC_QT_FC_MAP.get(cdc)
            if qt_fc:
                return qt_fc
        fc = (getattr(da, "fc", "") or "").strip()
        if fc:
            return fc
        mapped_fc = self._DA_NAME_FC_MAP.get(da.name)
        if mapped_fc:
            return mapped_fc
        return self._CDC_DEFAULT_FC_MAP.get(cdc, "CF")

    def _resolve_btype(self, da, do_name: str, cdc: str, ln_type_id: str) -> tuple:
        if da.name == "q":
            return ("Quality", None)
        if da.name == "t":
            return ("Timestamp", None)
        if da.name == "ctlModel":
            return ("Enum", "ctlModel")
        if da.name == "dU":
            # IEC 61850-6 SCL: dU (描述) 是 Unicode 字符串
            return ("Unicode255", None)
        if da.sub_das:
            return ("Struct", f"{ln_type_id}.{do_name}.{da.name}")
        if da.name in self._STRUCT_DA_DEFAULT_BDAS:
            return ("Struct", f"{ln_type_id}.{do_name}.{da.name}")
        # 根据 CDC 推断已知结构体 DA（即使在线发现未展开 sub_das）
        if cdc in self._CDC_BTYPE_MAP and da.name in self._CDC_BTYPE_MAP[cdc]:
            cdc_btype, _ = self._CDC_BTYPE_MAP[cdc][da.name]
            if cdc_btype == "Struct":
                return ("Struct", f"{ln_type_id}.{do_name}.{da.name}")
        btype = self._IEC_TYPE_TO_BTYPE.get(da.iec_type, "INT32")
        if da.name in ("stVal", "ctlVal"):
            if do_name in ("Mod", "Beh"):
                return ("Enum", "BehKind")
            if do_name == "Health":
                return ("Enum", "HealthKind")
        return (btype, None)

    def _build_fixed_do_type(self, ln_class: str, do_name: str) -> dict[str, Any] | None:
        if do_name == "Mod":
            return {
                "@id": f"_ENC_{ln_class}_Mod",
                "@cdc": "ENC",
                "DA": [
                    {"@name": "stVal", "@fc": "ST", "@bType": "Enum", "@type": "BehKind"},
                    {"@name": "ctlVal", "@fc": "CO", "@bType": "Enum", "@type": "BehKind"},
                    {"@name": "q", "@fc": "ST", "@bType": "Quality"},
                    {"@name": "t", "@fc": "ST", "@bType": "Timestamp"},
                    {"@name": "ctlModel", "@fc": "CF", "@bType": "Enum", "@type": "ctlModel"},
                ],
            }
        if do_name == "Beh":
            return {
                "@id": f"_ENC_{ln_class}_Beh",
                "@cdc": "ENC",
                "DA": [
                    {"@name": "stVal", "@fc": "ST", "@bType": "Enum", "@type": "BehKind"},
                    {"@name": "q", "@fc": "ST", "@bType": "Quality"},
                    {"@name": "t", "@fc": "ST", "@bType": "Timestamp"},
                ],
            }
        if do_name == "Health":
            return {
                "@id": f"_ENC_{ln_class}_Health",
                "@cdc": "ENC",
                "DA": [
                    {"@name": "stVal", "@fc": "ST", "@bType": "Enum", "@type": "HealthKind"},
                    {"@name": "q", "@fc": "ST", "@bType": "Quality"},
                    {"@name": "t", "@fc": "ST", "@bType": "Timestamp"},
                ],
            }
        if do_name == "NamPlt" and ln_class == "LLN0":
            return {
                "@id": f"_LPL_{ln_class}_NamPlt",
                "@cdc": "LPL",
                "DA": [
                    {"@name": "vendor", "@fc": "DC", "@bType": "VisString255"},
                    {"@name": "swRev", "@fc": "DC", "@bType": "VisString255"},
                    {"@name": "d", "@fc": "DC", "@bType": "VisString255"},
                ],
            }
        return None

    def _get_fixed_dos(self, ln_class: str) -> list[dict[str, Any]]:
        dos = []
        if ln_class != "LLN0":
            dos.append({"@name": "Mod", "@type": f"_ENC_{ln_class}_Mod"})
        dos.append({"@name": "Beh", "@type": f"_ENC_{ln_class}_Beh"})
        dos.append({"@name": "Health", "@type": f"_ENC_{ln_class}_Health"})
        if ln_class == "LLN0":
            dos.append({"@name": "NamPlt", "@type": f"_LPL_{ln_class}_NamPlt"})
        return dos
