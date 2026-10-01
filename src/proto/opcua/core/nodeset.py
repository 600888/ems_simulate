"""Validate the lossless M1 subset of NodeSet XML in an offline asyncua server."""

from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from xml.etree import ElementTree as ET

from asyncua import Server, ua

from src.proto.opcua.core.model import validate_variable

NODESET_NS = "http://opcfoundation.org/UA/2011/03/UANodeSet.xsd"
TYPES_NS = "http://opcfoundation.org/UA/2008/02/Types.xsd"
MAX_NODESET_BYTES = 5 * 1024 * 1024
MAX_MODEL_NODES = 10000
_TAG = f"{{{NODESET_NS}}}"
_DATA_TYPES = {"i=1": "Boolean", "i=6": "Int32", "i=11": "Double"}


@dataclass(frozen=True)
class ScalarNodeSet:
    sha256: str
    namespace_uri: str
    definitions: list[dict[str, Any]]


def _parse_xml(content: bytes) -> ScalarNodeSet:
    if not content or len(content) > MAX_NODESET_BYTES:
        raise ValueError("NodeSet XML 为空或超过 5 MB")
    try:
        xml = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("NodeSet XML 必须使用 UTF-8 编码") from exc
    if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        raise ValueError("NodeSet XML 不允许 DTD 或实体声明")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError(f"NodeSet XML 格式错误: {exc}") from exc
    if root.tag != f"{_TAG}UANodeSet":
        raise ValueError("文件必须是 OPC UA UANodeSet XML")
    namespaces = root.findall(f"{_TAG}NamespaceUris/{_TAG}Uri")
    if len(namespaces) != 1 or not namespaces[0].text or len(namespaces[0].text) > 255:
        raise ValueError("M1 NodeSet XML 必须包含一个非空命名空间 URI")
    namespace_uri = namespaces[0].text
    aliases: dict[str, str] = {}
    for item in root.findall(f"{_TAG}Aliases/{_TAG}Alias"):
        name = item.attrib.get("Alias")
        if not name or not item.text or name in aliases:
            raise ValueError("NodeSet XML Alias 缺少名称、目标或名称重复")
        aliases[name] = item.text

    def resolve(value: str) -> str:
        for _ in range(8):
            if value not in aliases:
                return value
            value = aliases[value] or ""
        raise ValueError("NodeSet XML Alias 存在循环或层级过深")

    definitions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for element in root:
        if element.tag in {f"{_TAG}NamespaceUris", f"{_TAG}Aliases"}:
            continue
        if element.tag != f"{_TAG}UAVariable":
            raise ValueError("M1 NodeSet XML 仅支持 Objects 下的标量变量，暂不支持对象、类型或扩展")
        label = element.attrib.get("NodeId", "")
        try:
            node_id = ua.NodeId.from_string(label)
        except (ua.UaStringParsingError, ValueError) as exc:
            raise ValueError(f"无效 NodeId: {label}") from exc
        if node_id.NamespaceIndex != 1 or not isinstance(node_id.Identifier, str) or not node_id.Identifier:
            raise ValueError(f"{label}: XML 节点必须是命名空间 1 的字符串 NodeId")
        browse_name = element.attrib.get("BrowseName", "")
        if not browse_name.startswith("1:"):
            raise ValueError(f"{label}: BrowseName 必须属于 XML 命名空间 1")
        browse_name = browse_name[2:]
        accepted_attributes = {"NodeId", "BrowseName", "ParentNodeId", "DataType", "AccessLevel", "UserAccessLevel"}
        defaults = {
            "ValueRank": "-1",
            "ArrayDimensions": "",
            "Historizing": "false",
            "MinimumSamplingInterval": "0",
            "WriteMask": "0",
            "UserWriteMask": "0",
        }
        for attribute, value in element.attrib.items():
            if attribute not in accepted_attributes and defaults.get(attribute) != value.lower():
                raise ValueError(f"{label}: 暂不支持属性 {attribute}={value}")
        if resolve(element.attrib.get("ParentNodeId", "i=85")) != "i=85":
            raise ValueError(f"{label}: M1 变量必须直接位于 Objects 下")
        access = element.attrib.get("AccessLevel", "1")
        user_access = element.attrib.get("UserAccessLevel", access)
        if access not in {"1", "3"} or user_access != access:
            raise ValueError(f"{label}: M1 仅支持只读或可读写变量，用户权限必须与访问级别一致")
        children = {child.tag for child in element}
        if children - {f"{_TAG}DisplayName", f"{_TAG}Description", f"{_TAG}References", f"{_TAG}Value"}:
            raise ValueError(f"{label}: 存在暂不支持的变量扩展")
        for field in ("DisplayName", "Description"):
            label_element = element.find(f"{_TAG}{field}")
            if label_element is not None and label_element.attrib:
                raise ValueError(f"{label}: M1 暂不支持本地化 {field}")
            text = element.findtext(f"{_TAG}{field}")
            if text and text != browse_name:
                raise ValueError(f"{label}: M1 {field} 必须与 BrowseName 一致")
        references = element.findall(f"{_TAG}References/{_TAG}Reference")
        parent_count = type_count = 0
        for reference in references:
            reference_type = resolve(reference.attrib.get("ReferenceType", ""))
            target = resolve(reference.text or "")
            direction = reference.attrib.get("IsForward", "true").lower()
            if direction not in {"true", "false"}:
                raise ValueError(f"{label}: IsForward 必须是 true 或 false")
            forward = direction == "true"
            if reference_type == "i=47" and target == "i=85" and not forward:
                parent_count += 1
            elif reference_type == "i=40" and target == "i=63" and forward:
                type_count += 1
            else:
                raise ValueError(f"{label}: 暂不支持的引用 {reference_type} → {target}")
        if parent_count != 1 or type_count != 1:
            raise ValueError(f"{label}: 必须包含一个 Objects 父引用和一个 BaseDataVariableType 引用")
        data_type = _DATA_TYPES.get(resolve(element.attrib.get("DataType", "i=24")))
        if data_type is None:
            raise ValueError(f"{label}: M1 仅支持 Boolean、Int32、Double")
        value_element = element.find(f"{_TAG}Value")
        values = list(value_element) if value_element is not None else []
        if len(values) != 1 or values[0].tag != f"{{{TYPES_NS}}}{data_type}":
            raise ValueError(f"{label}: 初始值类型与 DataType 不匹配或缺少初始值")
        text = values[0].text or ""
        try:
            if data_type == "Boolean":
                if text not in {"true", "false", "0", "1"}:
                    raise ValueError("无效 Boolean")
                value = text in {"true", "1"}
            else:
                value = int(text) if data_type == "Int32" else float(text)
            normalized = validate_variable(
                {
                    "node_id": f"ns=2;s={node_id.Identifier}",
                    "browse_name": browse_name,
                    "data_type": data_type,
                    "initial_value": value,
                    "writable": access == "3",
                }
            )
        except ValueError as exc:
            raise ValueError(f"{label}: {exc}") from exc
        if normalized["node_id"] in seen:
            raise ValueError(f"{label}: 重复 NodeId")
        seen.add(normalized["node_id"])
        definitions.append({"namespace_uri": namespace_uri, **normalized})
        if len(definitions) > MAX_MODEL_NODES:
            raise ValueError("NodeSet XML 最多 10000 个变量")
    if not definitions:
        raise ValueError("NodeSet XML 没有可导入的变量")
    return ScalarNodeSet(sha256(content).hexdigest(), namespace_uri, definitions)


async def inspect_nodeset(content: bytes) -> ScalarNodeSet:
    parsed = _parse_xml(content)
    server = Server()
    try:
        await server.init()
        imported = await server.import_xml(
            xmlstring=content.decode("utf-8-sig"), strict_mode=True, auto_load_definitions=False
        )
        if len(imported) != len(parsed.definitions):
            raise ValueError("NodeSet XML 导入数量不一致")
        index = await server.get_namespace_index(parsed.namespace_uri)
        for definition in parsed.definitions:
            identifier = ua.NodeId.from_string(definition["node_id"]).Identifier
            node = server.get_node(ua.NodeId(identifier, index))
            value = await node.read_data_value()
            if value.Value is None or value.Value.Value != definition["initial_value"]:
                raise ValueError(f"{definition['node_id']}: XML 初始值未能正确导入")
            if value.Value.VariantType.name != definition["data_type"]:
                raise ValueError(f"{definition['node_id']}: XML 数据类型未能正确导入")
            browse_name = await node.read_browse_name()
            access = await node.read_attribute(ua.AttributeIds.AccessLevel)
            if browse_name.Name != definition["browse_name"] or browse_name.NamespaceIndex != index:
                raise ValueError(f"{definition['node_id']}: XML BrowseName 未能正确导入")
            expected_access = 3 if definition["writable"] else 1
            if access.Value is None or access.Value.Value != expected_access:
                raise ValueError(f"{definition['node_id']}: XML 访问权限未能正确导入")
    except (ua.UaError, UnicodeDecodeError) as exc:
        raise ValueError(f"NodeSet XML 验证失败: {exc}") from exc
    finally:
        await server.stop()
    return parsed
