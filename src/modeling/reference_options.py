"""Context-aware reference choices for the generic modeling property form."""

from __future__ import annotations

from typing import Any

from src.modeling.document import ModelDocument, ModelNode


def contextualize_node_schema(
    document: ModelDocument,
    node: ModelNode,
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Turn resolvable reference fields into filtered select controls."""

    choices: dict[str, list[str]] = {}
    if node.kind in {"LN0", "LN"}:
        ln_class = "LLN0" if node.kind == "LN0" else str(node.attributes.get("lnClass") or "")
        choices["lnType"] = _type_ids(document, "LNODE_TYPE", ln_class=ln_class)
    elif node.kind in {"DO_DEF", "SDO_DEF"}:
        choices["type"] = _type_ids(document, "DO_TYPE")
    elif node.kind in {"DA_DEF", "BDA_DEF"}:
        basic_type = str(node.attributes.get("bType") or "")
        if basic_type == "Struct":
            choices["type"] = _type_ids(document, "DA_TYPE")
        elif basic_type == "Enum":
            choices["type"] = _type_ids(document, "ENUM_TYPE")
    elif node.kind in {"REPORT_CONTROL", "GSE_CONTROL", "SAMPLED_VALUE_CONTROL"}:
        choices["datSet"] = sorted(child.name for child in document.children(node.parent_id) if child.kind == "DATASET")
    elif node.kind == "CONNECTED_AP":
        choices["iedName"] = sorted(item.name for item in document.nodes if item.kind == "IED")
    elif node.kind == "FCDA":
        choices.update(_fcda_choices(document, node))

    if not choices:
        return schema
    for field in schema["fields"]:
        options = choices.get(field["key"])
        if options is not None:
            field["component"] = "select"
            field["options"] = options
    return schema


def _type_ids(document: ModelDocument, kind: str, *, ln_class: str = "") -> list[str]:
    values = []
    for node in document.nodes:
        if node.kind != kind:
            continue
        if ln_class and str(node.attributes.get("lnClass") or "") != ln_class:
            continue
        values.append(str(node.attributes.get("id") or node.name))
    return sorted(set(values))


def _fcda_choices(document: ModelDocument, fcda: ModelNode) -> dict[str, list[str]]:
    by_id = {node.id: node for node in document.nodes}
    owner_ied = _ancestor(fcda, by_id, "IED")
    if owner_ied is None:
        return {}
    logical_devices = [
        node for node in document.nodes if node.kind == "LDEVICE" and _ancestor(node, by_id, "IED") is owner_ied
    ]
    choices: dict[str, list[str]] = {
        "ldInst": sorted(str(node.attributes.get("inst") or node.name) for node in logical_devices)
    }
    target_ld_inst = str(fcda.attributes.get("ldInst") or "")
    target_ld = next(
        (node for node in logical_devices if str(node.attributes.get("inst") or node.name) == target_ld_inst),
        None,
    )
    if target_ld is None:
        return choices

    logical_nodes = [node for node in document.children(target_ld.id) if node.kind in {"LN0", "LN"}]
    choices["lnClass"] = sorted(
        {"LLN0" if node.kind == "LN0" else str(node.attributes.get("lnClass") or "") for node in logical_nodes}
    )
    target_ln = next(
        (
            node
            for node in logical_nodes
            if _logical_node_identity(node)
            == (
                str(fcda.attributes.get("prefix") or ""),
                str(fcda.attributes.get("lnClass") or ""),
                str(fcda.attributes.get("lnInst") or ""),
            )
        ),
        None,
    )
    if target_ln is None:
        return choices

    lnode_types = {
        str(node.attributes.get("id") or node.name): node for node in document.nodes if node.kind == "LNODE_TYPE"
    }
    do_types = {str(node.attributes.get("id") or node.name): node for node in document.nodes if node.kind == "DO_TYPE"}
    da_types = {str(node.attributes.get("id") or node.name): node for node in document.nodes if node.kind == "DA_TYPE"}
    lnode_type = lnode_types.get(str(target_ln.attributes.get("lnType") or ""))
    if lnode_type is None:
        return choices
    do_definitions = [node for node in document.children(lnode_type.id) if node.kind == "DO_DEF"]
    choices["doName"] = sorted(node.name for node in do_definitions)
    target_do = next((node for node in do_definitions if node.name == fcda.attributes.get("doName")), None)
    if target_do is None:
        return choices
    do_type = do_types.get(str(target_do.attributes.get("type") or ""))
    if do_type is not None:
        choices["daName"] = _data_attribute_paths(document, do_type, da_types)
    return choices


def _ancestor(
    node: ModelNode,
    by_id: dict[str, ModelNode],
    kind: str,
) -> ModelNode | None:
    current = node
    while current.parent_id:
        current = by_id.get(current.parent_id)
        if current is None:
            return None
        if current.kind == kind:
            return current
    return None


def _logical_node_identity(node: ModelNode) -> tuple[str, str, str]:
    if node.kind == "LN0":
        return ("", "LLN0", "")
    return (
        str(node.attributes.get("prefix") or ""),
        str(node.attributes.get("lnClass") or ""),
        str(node.attributes.get("inst") or ""),
    )


def _data_attribute_paths(
    document: ModelDocument,
    do_type: ModelNode,
    da_types: dict[str, ModelNode],
) -> list[str]:
    paths: list[str] = []
    for data_attribute in document.children(do_type.id):
        if data_attribute.kind != "DA_DEF":
            continue
        paths.append(data_attribute.name)
        if data_attribute.attributes.get("bType") == "Struct":
            da_type = da_types.get(str(data_attribute.attributes.get("type") or ""))
            if da_type is not None:
                paths.extend(
                    f"{data_attribute.name}.{path}" for path in _basic_data_attribute_paths(document, da_type, da_types)
                )
    return sorted(set(paths))


def _basic_data_attribute_paths(
    document: ModelDocument,
    da_type: ModelNode,
    da_types: dict[str, ModelNode],
) -> list[str]:
    paths: list[str] = []
    for basic_attribute in document.children(da_type.id):
        if basic_attribute.kind != "BDA_DEF":
            continue
        paths.append(basic_attribute.name)
        if basic_attribute.attributes.get("bType") == "Struct":
            nested = da_types.get(str(basic_attribute.attributes.get("type") or ""))
            if nested is not None:
                paths.extend(
                    f"{basic_attribute.name}.{path}" for path in _basic_data_attribute_paths(document, nested, da_types)
                )
    return paths
