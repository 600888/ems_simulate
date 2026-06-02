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
        **kwargs,
    ) -> str:
        """导出 ICD 文件 (IEC 61850 SCL 标准格式)

        输出结构:
            SCL
            ├── Header
            ├── Communication (含 IP 地址)
            ├── IED
            │   └── AccessPoint > Server
            │       └── LDevice
            │           ├── LN0 (含 DataSet / ReportControl)
            │           └── LN (含 DOI / DAI)
            └── DataTypeTemplates
                ├── LNodeType
                ├── DOType
                ├── DAType
                └── EnumType
        """
        if not ied_name:
            if model.lds:
                parts = model.lds[0].name.rsplit("_", 1)
                ied_name = parts[0] if len(parts) > 1 else model.lds[0].name
            else:
                ied_name = "IED"

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
        "mag": "MX", "cVal": "MX", "instMag": "MX", "mxVal": "MX",
        "fCVal": "MX", "setMag": "SP", "setVal": "SP", "wVal": "SP",
        "stVal": "ST", "general": "ST", "Cnt": "ST", "frVal": "ST",
        "frTm": "ST", "actVal": "ST", "subVal": "SV", "subEna": "SV",
        "ctlVal": "CO", "Oper": "CO", "SBO": "CO", "SBOw": "CO",
        "Cancel": "CO", "origin": "OR", "ctlNum": "CO", "AddCause": "CO",
        "valWTr": "CO", "q": "MX", "t": "MX", "blkEna": "BL",
        "dU": "DC", "du": "DC", "vendor": "DC", "swRev": "DC",
        "configRev": "DC", "d": "DC", "lnNs": "DC", "ctlModel": "CF",
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
            ld_inst = self._extract_ld_inst(ld.name, ied_name)
            ln0_item = None
            ln_list = []
            for ln in ld.lns:
                ln_type_id = f"{ied_name}{ld_inst}.{ln.name}"
                ln_inst = self._extract_ln_inst(ln.name)
                ln_class = ln.ln_class or self._extract_ln_class_from_name(ln.name)
                if ln_class == "LLN0":
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
        lnode_types = []
        do_types = []
        da_types = []
        enum_types = {}

        # 标准 CTL 枚举
        enum_types["ctlModel"] = [
            {"@ord": str(i), "#text": v}
            for i, v in enumerate([
                "status-only", "direct-with-normal-security",
                "sbo-with-normal-security", "direct-with-enhanced-security",
                "sbo-with-enhanced-security",
            ])
        ]
        enum_types["orCategory"] = [
            {"@ord": str(i), "#text": v}
            for i, v in enumerate([
                "not-supported", "bay-control", "station-control",
                "remote-control", "automatic-control", "maintenance-control",
            ])
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

        fixed_do_types_created: set[str] = set()

        for ld in model.lds:
            ld_inst = self._extract_ld_inst(ld.name, ied_name)
            for ln in ld.lns:
                ln_type_id = f"{ied_name}{ld_inst}.{ln.name}"
                ln_class = ln.ln_class or self._extract_ln_class_from_name(ln.name)
                do_refs = []

                for do in ln.dos:
                    cdc = self._infer_cdc_from_do(do.name, ln_class)
                    do_type_id = f"{ln_type_id}.{do.name}"
                    do_refs.append({"@name": do.name, "@type": do_type_id})

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

                        if da.sub_das:
                            da_type_id = f"{ln_type_id}.{do.name}.{da.name}"
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
                        elif da.name in self._STRUCT_DA_DEFAULT_BDAS:
                            # 在线发现未展开子 DA，使用默认 BDA 定义
                            da_type_id = f"{ln_type_id}.{do.name}.{da.name}"
                            bda_refs = []
                            for bda_name, bda_btype in self._STRUCT_DA_DEFAULT_BDAS[da.name]:
                                bda_ref = {"@name": bda_name, "@bType": bda_btype}
                                bda_refs.append(bda_ref)
                            da_type_item = {"@id": da_type_id}
                            da_type_item["BDA"] = bda_refs if len(bda_refs) > 1 else bda_refs[0]
                            da_types.append(da_type_item)

                    if da_refs:
                        do_type_item["DA"] = da_refs if len(da_refs) > 1 else da_refs[0]
                    do_types.append(do_type_item)

                # 固定 DO (Mod/Beh/Health/NamPlt)
                existing_fixed_do_names = {d.get("@name") for d in do_refs}
                for fixed_do in self._get_fixed_dos(ln_class):
                    fixed_do_type_id = fixed_do.get("@type", "")
                    if fixed_do_type_id and fixed_do_type_id not in fixed_do_types_created:
                        fixed_do_types_created.add(fixed_do_type_id)
                        do_type_item = self._build_fixed_do_type(ln_class, fixed_do.get("@name", ""))
                        if do_type_item:
                            do_types.append(do_type_item)
                    if fixed_do.get("@name") not in existing_fixed_do_names:
                        do_refs.append(fixed_do)

                lnode_type = {"@id": ln_type_id, "@lnClass": ln_class}
                if do_refs:
                    lnode_type["DO"] = do_refs if len(do_refs) > 1 else do_refs[0]
                lnode_types.append(lnode_type)

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
            dai_list = []
            for da in do.das:
                if da.name in ("dU", "du") and da.iec_type == IecType.STRING:
                    dai_list.append({"@name": da.name})
            if dai_list:
                doi["DAI"] = dai_list if len(dai_list) > 1 else dai_list[0]
            doi_list.append(doi)
        return doi_list if len(doi_list) > 1 else (doi_list[0] if doi_list else [])

    def _build_datasets(self, datasets, ld_inst: str, ln, discovered_lns) -> Any:
        discovered_ln_names: set[str] = set()
        for dln in discovered_lns:
            dln_class = dln.ln_class or self._extract_ln_class_from_name(dln.name) or ""
            dln_inst = self._extract_ln_inst(dln.name)
            discovered_ln_names.add(f"{dln_class}{dln_inst}")
            # LN 的 MMS 原始名称也加入匹配（FCDA 从 MMS ref 提取的 lnClass 可能不完整）
            discovered_ln_names.add(dln.name)

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

                ln_key = f"{fcda.get('@lnClass', '')}{fcda.get('@lnInst', '')}"
                if ln_key not in discovered_ln_names:
                    continue
                fcda_list.append(fcda)

            if fcda_list:
                ds_item["FCDA"] = fcda_list if len(fcda_list) > 1 else fcda_list[0]
                ds_list.append(ds_item)
        return ds_list if len(ds_list) > 1 else (ds_list[0] if ds_list else [])

    def _build_report_controls(self, rcb_list) -> Any:
        rcb_items = []
        for rcb in rcb_list:
            buffered = "true" if rcb.rcb_type == "BRCB" else "false"
            rcb_items.append({
                "@name": rcb.name,
                "@rptID": rcb.name,
                "@buffered": buffered,
                "@bufTime": "0",
                "@confRev": "1",
                "TrgOps": {"@dchg": "true", "@qchg": "false", "@dupd": "false", "@period": "false"},
                "OptFields": {
                    "@seqNum": "false", "@timeStamp": "false", "@dataSet": "false",
                    "@reasonCode": "false", "@dataRef": "false", "@entryID": "false", "@configRef": "false",
                },
                "RptEnabled": {"@max": "1"},
            })
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
                                    bda_list = [{"@name": bda.name, "@path": bda.path, "@fc": bda.fc, "@iecType": bda.iec_type} for bda in da.sub_das]
                                    da_item["SubDataAttributes"] = {"SubDataAttribute": bda_list if len(bda_list) > 1 else bda_list[0]}
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
                    ln_item["ReportControlBlocks"] = {"ReportControlBlock": rcb_list if len(rcb_list) > 1 else rcb_list[0]}
                if ln.gocb_list:
                    gocb_list = [{"@name": gocb.name, "@ref": gocb.ref} for gocb in ln.gocb_list]
                    ln_item["GooseControlBlocks"] = {"GooseControlBlock": gocb_list if len(gocb_list) > 1 else gocb_list[0]}
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

    def _extract_ld_inst(self, ld_name: str, ied_name: str) -> str:
        if ld_name.startswith(ied_name + "_"):
            return ld_name[len(ied_name) + 1:]
        if ld_name.startswith(ied_name):
            return ld_name[len(ied_name):]
        return ld_name

    def _extract_ln_inst(self, ln_name: str) -> str:
        if ln_name == "LLN0":
            return ""
        m = re.search(r"(\d+)$", ln_name)
        return m.group(1) if m else "1"

    def _extract_ln_class_from_name(self, ln_name: str) -> str:
        if ln_name == "LLN0":
            return "LLN0"
        m = re.match(r"^[A-Z]*(\d+)?([A-Z]+)\d*$", ln_name)
        if m:
            return m.group(2)
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
