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
        xml_str = xmltodict.unparse(scl_dict, pretty=pretty, indent="\t")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xml_str)
        return output_path

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
    }

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
        "ctlModel": "CF",
        "dbRef": "CF",
    }

    def _model_to_scl_dict(self, model: IedModel, ied_name: str) -> dict[str, Any]:
        type_templates = self._build_data_type_templates(model, ied_name)
        ied = self._build_ied_section(model, ied_name, type_templates)
        communication = {
            "SubNetwork": {
                "@name": "MMS",
                "@type": "8-MMS",
                "ConnectedAP": {
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
                },
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
                ln_type_id = f"{ied_name}{ld_inst}.{ln.name}"
                ln_inst = self._extract_ln_inst(ln.name)
                ln_class = ln.ln_class or self._extract_ln_class_from_name(ln.name)
                ln_prefix = self._extract_ln_prefix(ln.name, ln_class)
                if ln_class == "LLN0":
                    # 跳过无实际数据的 LLN0 系统节点 (无 DO/DataSet/RCB)
                    if not ln.dos and not ln.datasets and not ln.rcb_list:
                        continue
                    ln0_item = {
                        "@lnType": ln_type_id,
                        "@lnClass": "LLN0",
                        "@inst": "",
                    }
                    if ln.datasets:
                        ln0_item["DataSet"] = self._build_datasets(ln.datasets, ld_inst, ln, ld.lns)
                    if ln.rcb_list:
                        ln0_item["ReportControl"] = self._build_report_controls(ln.rcb_list)
                else:
                    ln_item = {
                        "@lnType": ln_type_id,
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
        return {
            "@name": ied_name,
            "Services": {
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
                "ConfLNs": {"@fixPrefix": "true", "@fixLnInst": "true"},
            },
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

        for ld in model.lds:
            ld_inst = self._get_ld_inst(ld, ied_name)
            for ln in ld.lns:
                ln_type_id = f"{ied_name}{ld_inst}.{ln.name}"
                ln_class = ln.ln_class or self._extract_ln_class_from_name(ln.name)
                do_refs = []

                for do in ln.dos:
                    cdc = self._infer_cdc_from_do(do.name, ln_class)
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

                # 跳过无实际 DO 的系统节点 (如 LLN0)
                if not do_refs and ln_class == "LLN0":
                    continue

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
                    "automatic-control",
                    "maintenance-control",
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
            fc = da.fc or self._DA_NAME_FC_MAP.get(da.name, "")
            btype, _ = self._resolve_btype(da, do.name, cdc, "")
            # 对于 Struct 类型，加上 BDA 指纹以区分不同子属性组合
            bda_fp = self._make_da_type_fingerprint(da) if btype == "Struct" else ()
            da_tuples.append((da.name, fc, btype, bda_fp))
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

        Returns:
            do_type_id: 共享的 DOType ID
        """
        fingerprint = self._make_do_type_fingerprint(do, cdc)
        if fingerprint in do_type_cache:
            return do_type_cache[fingerprint]

        do_type_id = _next_do_type_id(cdc)
        do_type_cache[fingerprint] = do_type_id

        do_type_item = {"@id": do_type_id, "@cdc": cdc}
        da_refs = []

        for da in do.das:
            fc = da.fc or self._DA_NAME_FC_MAP.get(da.name, "")
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
            if da.sub_das:
                da_type_id = self._resolve_or_create_da_type(da, da_type_cache, da_types)
                da_ref["@type"] = da_type_id
            elif da.name in self._STRUCT_DA_DEFAULT_BDAS:
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
            bda_tuples = tuple(
                sorted((bda.name, self._IEC_TYPE_TO_BTYPE.get(bda.iec_type, "INT32")) for bda in da.sub_das)
            )
            return bda_tuples
        if da.name in self._STRUCT_DA_DEFAULT_BDAS:
            bda_tuples = tuple(sorted((name, btype) for name, btype in self._STRUCT_DA_DEFAULT_BDAS[da.name]))
            return bda_tuples
        return ()

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
            bda_btype = self._IEC_TYPE_TO_BTYPE.get(bda.iec_type, "INT32")
            bda_ref = {"@name": bda.name, "@bType": bda_btype}
            if bda.iec_type == IecType.INTEGER and bda.name == "orCat":
                bda_ref["@bType"] = "Enum"
                bda_ref["@type"] = "orCategory"
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
        doi_list = []
        for do in ln.dos:
            doi = {"@name": do.name}
            # 从客户端读取的 dU 描述值填充 DAI
            du_val = self._do_descriptions.get(do.ref, "") if self._do_descriptions else ""
            if du_val:
                doi["DAI"] = {"@name": "dU", "Val": du_val}
            doi_list.append(doi)
        return doi_list if len(doi_list) > 1 else (doi_list[0] if doi_list else [])

    def _build_datasets(self, datasets, ld_inst: str, ln, discovered_lns) -> Any:
        # 构建 LN 索引: (lnClass, lnInst) → discovered LN
        # 同时构建所有 DO 名称集合用于灵活匹配
        ln_index: dict[str, Any] = {}
        all_do_names: set[str] = set()
        for dln in discovered_lns:
            dln_class = dln.ln_class or self._extract_ln_class_from_name(dln.name) or ""
            dln_inst = self._extract_ln_inst(dln.name)
            ln_index[f"{dln_class}{dln_inst}"] = dln
            ln_index[dln.name] = dln
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
                    "@prefix": "",
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
                ln_key = f"{fcda.get('@lnClass', '')}{fcda.get('@lnInst', '')}"

                if ln_key in ln_index:
                    # Normalize with discovered LN metadata after an exact match.
                    self._normalize_fcda_ln(fcda, ln_index[ln_key])
                elif fcda_do_name in all_do_names:
                    # 通过 DO 名称匹配到模型：查找拥有该 DO 的 LN
                    matched_ln = self._find_ln_by_do_name(discovered_lns, fcda_do_name)
                    if matched_ln is not None:
                        # Update FCDA lnClass/lnInst from the discovered LN.
                        self._normalize_fcda_ln(fcda, matched_ln)
                    else:
                        # DO 名匹配也失败，跳过此 FCDA
                        continue
                else:
                    continue
                fcda_list.append(fcda)

            if fcda_list:
                ds_item["FCDA"] = fcda_list if len(fcda_list) > 1 else fcda_list[0]
                ds_list.append(ds_item)
        return ds_list if len(ds_list) > 1 else (ds_list[0] if ds_list else [])

    @staticmethod
    def _find_ln_by_do_name(discovered_lns, do_name: str):
        """通过 DO 名称查找所属的逻辑节点"""
        for dln in discovered_lns:
            for do in dln.dos:
                if do.name == do_name:
                    return dln
        return None

    def _build_report_controls(self, rcb_list) -> Any:
        rcb_items = []
        for rcb in rcb_list:
            buffered = "true" if rcb.rcb_type == "BRCB" else "false"
            rcb_items.append(
                {
                    "@name": rcb.name,
                    "@rptID": rcb.name,
                    "@buffered": buffered,
                    "@bufTime": "0",
                    "@confRev": "1",
                    "TrgOps": {"@dchg": "true", "@qchg": "false", "@dupd": "false", "@period": "false"},
                    "OptFields": {
                        "@seqNum": "false",
                        "@timeStamp": "false",
                        "@dataSet": "false",
                        "@reasonCode": "false",
                        "@dataRef": "false",
                        "@entryID": "false",
                        "@configRef": "false",
                    },
                    "RptEnabled": {"@max": "1"},
                }
            )
        return rcb_items if len(rcb_items) > 1 else (rcb_items[0] if rcb_items else [])

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

        if len(ld_names) > 1:
            prefix = os.path.commonprefix(ld_names).rstrip("_-. ")
            if prefix and all(self._looks_like_ld_inst(name[len(prefix) :]) for name in ld_names):
                return prefix

        suffix_split = self._split_known_ld_suffix(ld_names[0])
        if suffix_split is not None:
            return suffix_split[0]

        parts = ld_names[0].split("_", 1)
        if len(parts) > 1 and parts[0]:
            return parts[0]
        return ld_names[0]

    def _get_ld_inst(self, ld, ied_name: str) -> str:
        ld_name = getattr(ld, "name", "") or ""
        ld_inst = getattr(ld, "inst", "") or ""
        if ld_inst and ld_inst != ld_name:
            return self._extract_ld_inst(ld_inst, ied_name)
        return self._extract_ld_inst(ld_name, ied_name)

    @staticmethod
    def _looks_like_ld_inst(value: str) -> bool:
        if not value:
            return False
        return bool(re.match(r"^(LD\d+|CTRL\d*|MEAS\d*|PROT\d*|CTMP\d*|BAY\d*|GOOSE\d*|MMS\d*)$", value))

    @staticmethod
    def _split_known_ld_suffix(ld_name: str) -> tuple[str, str] | None:
        match = re.match(r"^(.+?)(LD\d+|CTRL\d*|MEAS\d*|PROT\d*|CTMP\d*|BAY\d*|GOOSE\d*|MMS\d*)$", ld_name)
        if not match:
            return None
        ied_name, ld_inst = match.groups()
        if not ied_name or not ld_inst:
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
        return "MV"

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
        # 根据 CDC 推断已知结构体 DA（即使在线发现未展开 sub_das）
        if cdc in self._CDC_BTYPE_MAP and da.name in self._CDC_BTYPE_MAP[cdc]:
            cdc_btype, _ = self._CDC_BTYPE_MAP[cdc][da.name]
            if cdc_btype == "Struct":
                return ("Struct", f"{ln_type_id}.{do_name}.{da.name}")
        btype = self._IEC_TYPE_TO_BTYPE.get(da.iec_type, "INT32")
        if do_name in ("Mod", "Beh", "Health") and da.name in ("stVal", "ctlVal"):
            return ("Enum", "Origin")
        return (btype, None)

    def _build_fixed_do_type(self, ln_class: str, do_name: str) -> dict[str, Any] | None:
        if do_name == "Mod":
            return {
                "@id": f"_ENC_{ln_class}_Mod",
                "@cdc": "ENC",
                "DA": [
                    {"@name": "stVal", "@fc": "ST", "@bType": "Enum", "@type": "BehKind"},
                    {"@name": "ctlVal", "@fc": "CO", "@bType": "Enum", "@type": "BehKind"},
                    {"@name": "q", "@fc": "MX", "@bType": "Quality"},
                    {"@name": "t", "@fc": "MX", "@bType": "Timestamp"},
                    {"@name": "ctlModel", "@fc": "CF", "@bType": "Enum", "@type": "ctlModel"},
                ],
            }
        if do_name == "Beh":
            return {
                "@id": f"_ENC_{ln_class}_Beh",
                "@cdc": "ENC",
                "DA": [
                    {"@name": "stVal", "@fc": "ST", "@bType": "Enum", "@type": "BehKind"},
                    {"@name": "q", "@fc": "MX", "@bType": "Quality"},
                    {"@name": "t", "@fc": "MX", "@bType": "Timestamp"},
                ],
            }
        if do_name == "Health":
            return {
                "@id": f"_ENC_{ln_class}_Health",
                "@cdc": "ENC",
                "DA": [
                    {"@name": "stVal", "@fc": "ST", "@bType": "Enum", "@type": "HealthKind"},
                    {"@name": "q", "@fc": "MX", "@bType": "Quality"},
                    {"@name": "t", "@fc": "MX", "@bType": "Timestamp"},
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
