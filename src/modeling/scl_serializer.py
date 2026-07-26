"""将可编辑模型树序列化为 IEC 61850-6 SCL XML。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
import xml.etree.ElementTree as ET

from src.data.model.iec61850_modeling import Iec61850ModelProject
from src.modeling.document import ModelNode as Iec61850ModelNode

SCL_NS = "http://www.iec.ch/61850/2003/SCL"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
ET.register_namespace("", SCL_NS)
ET.register_namespace("xsi", XSI_NS)


def _json_loads(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _tag(name: str) -> str:
    return f"{{{SCL_NS}}}{name}"


def _bool(value: object) -> str:
    return "true" if bool(value) else "false"


def _value_or_default(source: dict, key: str, default: object) -> object:
    value = source.get(key)
    return default if value is None or value == "" else value


def _attrs(source: dict, keys: tuple[str, ...], *, rename: dict[str, str] | None = None) -> dict[str, str]:
    result: dict[str, str] = {}
    rename = rename or {}
    for key in keys:
        value = source.get(key)
        if value is not None and value != "":
            result[rename.get(key, key)] = _bool(value) if isinstance(value, bool) else str(value)
    return result


@dataclass(slots=True)
class SclSerializationResult:
    xml: str
    filename: str


class SclModelSerializer:
    """把通用节点持久化模型映射为标准 SCL 元素层级。"""

    def serialize(
        self,
        project: Iec61850ModelProject,
        nodes: list[Iec61850ModelNode],
        *,
        file_type: str | None = None,
    ) -> SclSerializationResult:
        children: dict[str | None, list[Iec61850ModelNode]] = defaultdict(list)
        for node in sorted(nodes, key=lambda item: (item.sort_order, item.name)):
            children[node.parent_id].append(node)
        root_node = next((node for node in nodes if node.kind == "ROOT"), None)
        if root_node is None:
            raise ValueError("模型缺少 ROOT 节点")

        version, revision = self._standard_identifiers(project.standard_version)
        root_attrs = _json_loads(root_node.attributes_json)
        scl_attrs: dict[str, str] = {}
        if root_attrs.get("emitEdition", True):
            scl_attrs.update({"version": version, "revision": revision})
        schema_location = root_attrs.get("schemaLocation")
        if schema_location:
            scl_attrs[f"{{{XSI_NS}}}schemaLocation"] = str(schema_location)
        scl = ET.Element(_tag("SCL"), scl_attrs)
        top_level = children.get(root_node.id, [])

        header_node = next((node for node in top_level if node.kind == "HEADER"), None)
        header_attrs = _json_loads(header_node.attributes_json) if header_node else {}
        header_values = {
            "id": str(header_attrs.get("id") or project.code),
            "version": str(_value_or_default(header_attrs, "version", "1")),
            "revision": str(_value_or_default(header_attrs, "revision", project.revision)),
            "toolID": str(header_attrs.get("toolID") or "EMS Simulator IEC61850 Modeler"),
            "nameStructure": str(header_attrs.get("nameStructure") or "IEDName"),
        }
        header = ET.SubElement(
            scl,
            _tag("Header"),
            header_values,
        )
        if header_node:
            self._append_header_children(header, header_node, children)

        communication = next((node for node in top_level if node.kind == "COMMUNICATION"), None)
        if communication:
            self._append_communication(scl, communication, children)

        for ied_node in (node for node in top_level if node.kind == "IED"):
            self._append_ied(scl, ied_node, children)

        templates_node = next((node for node in top_level if node.kind == "DATA_TYPE_TEMPLATES"), None)
        templates = ET.SubElement(scl, _tag("DataTypeTemplates"))
        if templates_node:
            self._append_templates(templates, children.get(templates_node.id, []), children)

        self._append_extensions(scl, top_level)

        ET.indent(scl, space="  ")
        xml_body = ET.tostring(scl, encoding="unicode", short_empty_elements=True)
        target_file_type = (file_type or project.file_type).lower()
        filename = f"{project.code}.{target_file_type}"
        return SclSerializationResult(
            xml=f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_body}\n',
            filename=filename,
        )

    @staticmethod
    def _standard_identifiers(standard_version: str) -> tuple[str, str]:
        normalized = standard_version.lower()
        if "ed1" in normalized:
            return "2003", "A"
        return "2007", "B"

    def _append_ied(
        self,
        parent: ET.Element,
        node: Iec61850ModelNode,
        children: dict[str | None, list[Iec61850ModelNode]],
    ) -> None:
        attrs = _json_loads(node.attributes_json)
        ied_attrs = {"name": node.name}
        ied_attrs.update(_attrs(attrs, ("desc", "type", "manufacturer", "configVersion")))
        ied = ET.SubElement(parent, _tag("IED"), ied_attrs)
        ied_children = children.get(node.id, [])
        services_node = next((child for child in ied_children if child.kind == "SERVICES"), None)
        if services_node:
            self._append_services(ied, services_node, children)
        for access_point_node in (child for child in ied_children if child.kind == "ACCESS_POINT"):
            access_attrs = _json_loads(access_point_node.attributes_json)
            access_point = ET.SubElement(
                ied,
                _tag("AccessPoint"),
                {"name": access_point_node.name, **_attrs(access_attrs, ("desc", "router", "clock"))},
            )
            server_node = next(
                (child for child in children.get(access_point_node.id, []) if child.kind == "SERVER"),
                None,
            )
            if not server_node:
                continue
            server_attrs = _json_loads(server_node.attributes_json)
            server = ET.SubElement(access_point, _tag("Server"), _attrs(server_attrs, ("desc", "timeout")))
            authentication = next(
                (child for child in children.get(server_node.id, []) if child.kind == "AUTHENTICATION"),
                None,
            )
            if authentication:
                ET.SubElement(server, _tag("Authentication"), _json_loads(authentication.attributes_json))
            for logical_device in (child for child in children.get(server_node.id, []) if child.kind == "LDEVICE"):
                self._append_logical_device(server, logical_device, children)
            self._append_extensions(server, children.get(server_node.id, []))
            self._append_extensions(access_point, children.get(access_point_node.id, []))
        self._append_extensions(ied, ied_children)

    def _append_header_children(
        self,
        parent: ET.Element,
        node: Iec61850ModelNode,
        children: dict[str | None, list[Iec61850ModelNode]],
    ) -> None:
        history_node = next((child for child in children.get(node.id, []) if child.kind == "HISTORY"), None)
        if history_node:
            history = ET.SubElement(parent, _tag("History"))
            for item in (child for child in children.get(history_node.id, []) if child.kind == "HITEM"):
                ET.SubElement(
                    history,
                    _tag("Hitem"),
                    _attrs(_json_loads(item.attributes_json), ("version", "revision", "when", "who", "what", "why")),
                )
        self._append_extensions(parent, children.get(node.id, []))

    def _append_services(
        self,
        parent: ET.Element,
        node: Iec61850ModelNode,
        children: dict[str | None, list[Iec61850ModelNode]],
    ) -> None:
        services = ET.SubElement(parent, _tag("Services"))
        for capability in (child for child in children.get(node.id, []) if child.kind == "SERVICE_CAPABILITY"):
            attrs = _json_loads(capability.attributes_json)
            raw = attrs.pop("xml", None)
            if raw:
                services.append(ET.fromstring(str(raw)))
                continue
            tag = str(attrs.pop("tag", "") or capability.name)
            attrs.pop("desc", None)
            ET.SubElement(
                services,
                _tag(tag),
                {
                    key: _bool(value) if isinstance(value, bool) else str(value)
                    for key, value in attrs.items()
                    if value not in (None, "")
                },
            )
        self._append_extensions(services, children.get(node.id, []))

    def _append_communication(
        self,
        parent: ET.Element,
        node: Iec61850ModelNode,
        children: dict[str | None, list[Iec61850ModelNode]],
    ) -> None:
        communication = ET.SubElement(parent, _tag("Communication"))
        for subnet_node in (child for child in children.get(node.id, []) if child.kind == "SUBNETWORK"):
            attrs = _json_loads(subnet_node.attributes_json)
            subnetwork = ET.SubElement(
                communication,
                _tag("SubNetwork"),
                {"name": subnet_node.name, **_attrs(attrs, ("desc", "type"))},
            )
            if attrs.get("bitRate") not in (None, ""):
                bit_rate = ET.SubElement(
                    subnetwork,
                    _tag("BitRate"),
                    _attrs(attrs, ("multiplier",)),
                )
                bit_rate.text = str(attrs["bitRate"])
            for connected_node in (child for child in children.get(subnet_node.id, []) if child.kind == "CONNECTED_AP"):
                connected_attrs = _json_loads(connected_node.attributes_json)
                connected_ap = ET.SubElement(
                    subnetwork,
                    _tag("ConnectedAP"),
                    {
                        "iedName": str(connected_attrs.get("iedName") or ""),
                        "apName": str(connected_attrs.get("apName") or ""),
                        **_attrs(connected_attrs, ("desc",)),
                    },
                )
                for child in children.get(connected_node.id, []):
                    if child.kind == "ADDRESS":
                        self._append_address(connected_ap, child, children)
                    elif child.kind in ("GSE", "SMV"):
                        service_attrs = _json_loads(child.attributes_json)
                        service = ET.SubElement(
                            connected_ap,
                            _tag(child.kind),
                            {
                                "ldInst": str(service_attrs.get("ldInst") or ""),
                                "cbName": str(service_attrs.get("cbName") or child.name),
                            },
                        )
                        address = next(
                            (item for item in children.get(child.id, []) if item.kind == "ADDRESS"),
                            None,
                        )
                        if address:
                            self._append_address(service, address, children)
                        if child.kind == "GSE":
                            for key, tag_name in (("minTime", "MinTime"), ("maxTime", "MaxTime")):
                                if service_attrs.get(key) not in (None, ""):
                                    ET.SubElement(service, _tag(tag_name)).text = str(service_attrs[key])
                self._append_extensions(connected_ap, children.get(connected_node.id, []))
            self._append_extensions(subnetwork, children.get(subnet_node.id, []))
        self._append_extensions(communication, children.get(node.id, []))

    @staticmethod
    def _append_address(
        parent: ET.Element,
        node: Iec61850ModelNode,
        children: dict[str | None, list[Iec61850ModelNode]],
    ) -> None:
        address = ET.SubElement(parent, _tag("Address"))
        for parameter in (child for child in children.get(node.id, []) if child.kind == "P"):
            attrs = _json_loads(parameter.attributes_json)
            value = ET.SubElement(address, _tag("P"), {"type": str(attrs.get("type") or parameter.name)})
            value.text = str(attrs.get("value") or "")
        SclModelSerializer._append_extensions(address, children.get(node.id, []))

    def _append_logical_device(
        self,
        parent: ET.Element,
        node: Iec61850ModelNode,
        children: dict[str | None, list[Iec61850ModelNode]],
    ) -> None:
        attrs = _json_loads(node.attributes_json)
        ld_attrs = {"inst": str(attrs.get("inst") or node.name)}
        ld_attrs.update(_attrs(attrs, ("desc",)))
        logical_device = ET.SubElement(parent, _tag("LDevice"), ld_attrs)
        for logical_node in (child for child in children.get(node.id, []) if child.kind in ("LN0", "LN")):
            self._append_logical_node(logical_device, logical_node, children)
        self._append_extensions(logical_device, children.get(node.id, []))

    def _append_logical_node(
        self,
        parent: ET.Element,
        node: Iec61850ModelNode,
        children: dict[str | None, list[Iec61850ModelNode]],
    ) -> None:
        attrs = _json_loads(node.attributes_json)
        if node.kind == "LN0":
            ln_attrs = {"lnClass": "LLN0", "inst": ""}
            if attrs.get("lnType"):
                ln_attrs["lnType"] = str(attrs["lnType"])
            if attrs.get("desc"):
                ln_attrs["desc"] = str(attrs["desc"])
            element = ET.SubElement(parent, _tag("LN0"), ln_attrs)
        else:
            ln_attrs = {
                "prefix": str(attrs.get("prefix") or ""),
                "lnClass": str(attrs.get("lnClass") or node.name[:4].upper()),
                "inst": str(attrs.get("inst") or "1"),
            }
            if attrs.get("lnType"):
                ln_attrs["lnType"] = str(attrs["lnType"])
            if attrs.get("desc"):
                ln_attrs["desc"] = str(attrs["desc"])
            element = ET.SubElement(parent, _tag("LN"), ln_attrs)

        for child in children.get(node.id, []):
            if child.kind == "DOI":
                self._append_doi(element, child, children)
            elif child.kind == "DATASET":
                self._append_dataset(element, child, children)
            elif child.kind == "REPORT_CONTROL":
                self._append_report_control(element, child, children)
            elif child.kind == "GSE_CONTROL":
                self._append_gse_control(element, child)
            elif child.kind == "SAMPLED_VALUE_CONTROL":
                self._append_sampled_value_control(element, child, children)
            elif child.kind == "INPUTS":
                self._append_inputs(element, child, children)
            elif child.kind == "SETTING_CONTROL":
                setting_attrs = _json_loads(child.attributes_json)
                ET.SubElement(element, _tag("SettingControl"), _attrs(setting_attrs, ("desc", "numOfSGs", "actSG")))
        self._append_extensions(element, children.get(node.id, []))

    def _append_doi(
        self,
        parent: ET.Element,
        node: Iec61850ModelNode,
        children: dict[str | None, list[Iec61850ModelNode]],
    ) -> None:
        attrs = _json_loads(node.attributes_json)
        doi = ET.SubElement(parent, _tag("DOI"), {"name": node.name, **_attrs(attrs, ("desc", "accessControl"))})
        for child in children.get(node.id, []):
            child_attrs = _json_loads(child.attributes_json)
            if child.kind == "DAI" and not child_attrs.get("_templateInherited"):
                self._append_dai(doi, child, children)
            elif child.kind == "SDI":
                self._append_sdi(doi, child, children)
        self._append_extensions(doi, children.get(node.id, []))

    def _append_sdi(
        self,
        parent: ET.Element,
        node: Iec61850ModelNode,
        children: dict[str | None, list[Iec61850ModelNode]],
    ) -> None:
        attrs = _json_loads(node.attributes_json)
        sdi = ET.SubElement(parent, _tag("SDI"), {"name": node.name, **_attrs(attrs, ("desc",))})
        for child in children.get(node.id, []):
            child_attrs = _json_loads(child.attributes_json)
            if child.kind == "DAI" and not child_attrs.get("_templateInherited"):
                self._append_dai(sdi, child, children)
            elif child.kind == "SDI":
                self._append_sdi(sdi, child, children)
        self._append_extensions(sdi, children.get(node.id, []))

    def _append_dai(
        self,
        parent: ET.Element,
        node: Iec61850ModelNode,
        children: dict[str | None, list[Iec61850ModelNode]],
    ) -> None:
        attrs = _json_loads(node.attributes_json)
        dai = ET.SubElement(parent, _tag("DAI"), {"name": node.name, **_attrs(attrs, ("desc", "sAddr", "valKind"))})
        value = attrs.get("value")
        if value is not None and value != "":
            ET.SubElement(dai, _tag("Val")).text = str(value)
        else:
            self._append_value(dai, node, attrs, children)
        self._append_extensions(dai, children.get(node.id, []))

    @staticmethod
    def _append_dataset(
        parent: ET.Element,
        node: Iec61850ModelNode,
        children: dict[str | None, list[Iec61850ModelNode]],
    ) -> None:
        attrs = _json_loads(node.attributes_json)
        dataset = ET.SubElement(parent, _tag("DataSet"), {"name": node.name, **_attrs(attrs, ("desc",))})
        for fcda_node in (child for child in children.get(node.id, []) if child.kind == "FCDA"):
            fcda_attrs = _json_loads(fcda_node.attributes_json)
            ET.SubElement(
                dataset,
                _tag("FCDA"),
                _attrs(fcda_attrs, ("ldInst", "prefix", "lnClass", "lnInst", "doName", "daName", "fc")),
            )
        SclModelSerializer._append_extensions(dataset, children.get(node.id, []))

    def _append_report_control(
        self,
        parent: ET.Element,
        node: Iec61850ModelNode,
        children: dict[str | None, list[Iec61850ModelNode]],
    ) -> None:
        attrs = _json_loads(node.attributes_json)
        values = {
            "name": node.name,
            "confRev": str(_value_or_default(attrs, "confRev", 1)),
            **_attrs(attrs, ("desc", "datSet", "rptID", "buffered", "bufTime", "intgPd")),
        }
        control = ET.SubElement(parent, _tag("ReportControl"), values)
        child_map = {child.kind: child for child in children.get(node.id, [])}
        trg = child_map.get("TRG_OPS")
        opt = child_map.get("OPT_FIELDS")
        enabled = child_map.get("RPT_ENABLED")
        if trg:
            ET.SubElement(
                control,
                _tag("TrgOps"),
                _attrs(_json_loads(trg.attributes_json), ("dchg", "qchg", "dupd", "period", "gi")),
            )
        if opt:
            ET.SubElement(
                control,
                _tag("OptFields"),
                _attrs(
                    _json_loads(opt.attributes_json),
                    (
                        "seqNum",
                        "timeStamp",
                        "reasonCode",
                        "dataSet",
                        "dataRef",
                        "bufOvfl",
                        "entryID",
                        "configRef",
                        "segmentation",
                    ),
                ),
            )
        if enabled:
            enabled_attrs = _json_loads(enabled.attributes_json)
            rpt_enabled = ET.SubElement(
                control,
                _tag("RptEnabled"),
                {"max": str(_value_or_default(enabled_attrs, "max", 1)), **_attrs(enabled_attrs, ("desc",))},
            )
            for client in (child for child in children.get(enabled.id, []) if child.kind == "CLIENT_LN"):
                ET.SubElement(rpt_enabled, _tag("ClientLN"), _json_loads(client.attributes_json))
        self._append_extensions(control, children.get(node.id, []))

    @staticmethod
    def _append_gse_control(parent: ET.Element, node: Iec61850ModelNode) -> None:
        attrs = _json_loads(node.attributes_json)
        values = {
            "name": node.name,
            "confRev": str(_value_or_default(attrs, "confRev", 1)),
            **_attrs(attrs, ("desc", "datSet", "appID", "fixedOffs", "type")),
        }
        ET.SubElement(parent, _tag("GSEControl"), values)

    def _append_sampled_value_control(
        self,
        parent: ET.Element,
        node: Iec61850ModelNode,
        children: dict[str | None, list[Iec61850ModelNode]],
    ) -> None:
        attrs = _json_loads(node.attributes_json)
        values = {
            "name": node.name,
            "confRev": str(_value_or_default(attrs, "confRev", 1)),
            **_attrs(
                attrs,
                (
                    "desc",
                    "datSet",
                    "smvID",
                    "multicast",
                    "smpRate",
                    "nofASDU",
                    "securityEnable",
                ),
            ),
        }
        control = ET.SubElement(parent, _tag("SampledValueControl"), values)
        options = next(
            (child for child in children.get(node.id, []) if child.kind == "SMV_OPTS"),
            None,
        )
        if options is not None:
            ET.SubElement(
                control,
                _tag("SmvOpts"),
                _attrs(
                    _json_loads(options.attributes_json),
                    (
                        "refreshTime",
                        "sampleSynchronized",
                        "sampleRate",
                        "dataSet",
                        "security",
                        "timestamp",
                        "synchSourceId",
                    ),
                ),
            )
        self._append_extensions(control, children.get(node.id, []))

    @staticmethod
    def _append_inputs(
        parent: ET.Element,
        node: Iec61850ModelNode,
        children: dict[str | None, list[Iec61850ModelNode]],
    ) -> None:
        inputs = ET.SubElement(parent, _tag("Inputs"))
        keys = (
            "iedName",
            "ldInst",
            "prefix",
            "lnClass",
            "lnInst",
            "doName",
            "daName",
            "intAddr",
            "serviceType",
            "srcLDInst",
            "srcPrefix",
            "srcLNClass",
            "srcLNInst",
            "srcCBName",
        )
        for ext_ref in (child for child in children.get(node.id, []) if child.kind == "EXT_REF"):
            ET.SubElement(inputs, _tag("ExtRef"), _attrs(_json_loads(ext_ref.attributes_json), keys))
        SclModelSerializer._append_extensions(inputs, children.get(node.id, []))

    def _append_templates(
        self,
        parent: ET.Element,
        template_nodes: list[Iec61850ModelNode],
        children: dict[str | None, list[Iec61850ModelNode]],
    ) -> None:
        for node in template_nodes:
            attrs = _json_loads(node.attributes_json)
            if node.kind == "LNODE_TYPE":
                element = ET.SubElement(
                    parent,
                    _tag("LNodeType"),
                    {
                        "id": str(attrs.get("id") or node.name),
                        "lnClass": str(attrs.get("lnClass") or "LLN0"),
                        **_attrs(attrs, ("desc", "iedType")),
                    },
                )
                for child in children.get(node.id, []):
                    if child.kind == "DO_DEF":
                        values = _json_loads(child.attributes_json)
                        ET.SubElement(
                            element,
                            _tag("DO"),
                            {"name": child.name, **_attrs(values, ("type", "transient", "desc"))},
                        )
            elif node.kind == "DO_TYPE":
                element = ET.SubElement(
                    parent,
                    _tag("DOType"),
                    {
                        "id": str(attrs.get("id") or node.name),
                        "cdc": str(attrs.get("cdc") or "SPS"),
                        **_attrs(attrs, ("desc", "iedType")),
                    },
                )
                for child in children.get(node.id, []):
                    values = _json_loads(child.attributes_json)
                    if child.kind == "DA_DEF":
                        da = ET.SubElement(
                            element,
                            _tag("DA"),
                            {
                                "name": child.name,
                                **_attrs(
                                    values, ("bType", "type", "fc", "dchg", "qchg", "dupd", "desc", "sAddr", "valKind")
                                ),
                            },
                        )
                        self._append_value(da, child, values, children)
                        self._append_extensions(da, children.get(child.id, []))
                    elif child.kind == "SDO_DEF":
                        ET.SubElement(element, _tag("SDO"), {"name": child.name, **_attrs(values, ("type", "desc"))})
            elif node.kind == "DA_TYPE":
                element = ET.SubElement(parent, _tag("DAType"), {"id": str(attrs.get("id") or node.name)})
                for child in children.get(node.id, []):
                    if child.kind == "BDA_DEF":
                        values = _json_loads(child.attributes_json)
                        bda = ET.SubElement(
                            element,
                            _tag("BDA"),
                            {"name": child.name, **_attrs(values, ("bType", "type", "desc", "sAddr"))},
                        )
                        self._append_value(bda, child, values, children)
                        self._append_extensions(bda, children.get(child.id, []))
            elif node.kind == "ENUM_TYPE":
                element = ET.SubElement(
                    parent, _tag("EnumType"), {"id": str(attrs.get("id") or node.name), **_attrs(attrs, ("desc",))}
                )
                for child in children.get(node.id, []):
                    if child.kind == "ENUM_VALUE":
                        values = _json_loads(child.attributes_json)
                        enum_value = ET.SubElement(element, _tag("EnumVal"), {"ord": str(values.get("ord") or 0)})
                        enum_value.text = str(values.get("value") or child.name)
            if node.kind in ("LNODE_TYPE", "DO_TYPE", "DA_TYPE", "ENUM_TYPE"):
                self._append_extensions(element, children.get(node.id, []))
        self._append_extensions(parent, template_nodes)

    @staticmethod
    def _append_value(
        parent: ET.Element,
        node: Iec61850ModelNode,
        attrs: dict,
        children: dict[str | None, list[Iec61850ModelNode]],
    ) -> None:
        value_nodes = [child for child in children.get(node.id, []) if child.kind == "VAL"]
        if value_nodes:
            for value_node in value_nodes:
                value_attrs = _json_loads(value_node.attributes_json)
                value = ET.SubElement(parent, _tag("Val"), _attrs(value_attrs, ("sGroup",)))
                value.text = str(value_attrs.get("value", ""))
        elif attrs.get("value") is not None and attrs.get("value") != "":
            ET.SubElement(parent, _tag("Val")).text = str(attrs["value"])

    @staticmethod
    def _append_extensions(parent: ET.Element, nodes: list[Iec61850ModelNode]) -> None:
        for node in (item for item in nodes if item.kind == "EXTENSION"):
            raw = _json_loads(node.attributes_json).get("xml")
            if not raw:
                continue
            try:
                parent.append(ET.fromstring(str(raw)))
            except ET.ParseError as exc:
                raise ValueError(f"扩展片段 {node.name} 不是合法 XML: {exc}") from exc
