"""Cross-layer semantic validation for editable IEC 61850 IED models."""

from __future__ import annotations

from dataclasses import dataclass

from src.modeling.document import ModelDocument, ModelNode


@dataclass(frozen=True, slots=True)
class SemanticIssue:
    level: str
    code: str
    message: str
    node: ModelNode
    field: str = ""


def validate_semantic_references(document: ModelDocument) -> list[SemanticIssue]:
    """Validate references that require traversing both instances and type templates."""

    issues: list[SemanticIssue] = []
    nodes = document.nodes
    by_id = {node.id: node for node in nodes}
    type_indexes = _build_type_indexes(nodes, issues)

    for logical_node in (node for node in nodes if node.kind in {"LN0", "LN"}):
        _validate_logical_node_type(logical_node, type_indexes["LNODE_TYPE"], issues)

    for control in (node for node in nodes if node.kind == "GSE_CONTROL"):
        parent = by_id.get(control.parent_id or "")
        if parent is None or parent.kind != "LN0":
            issues.append(
                SemanticIssue(
                    "ERROR",
                    "GSE_CONTROL_REQUIRES_LN0",
                    "GSEControl 只能配置在 LLN0 下",
                    control,
                )
            )

    for control in (node for node in nodes if node.kind == "SAMPLED_VALUE_CONTROL"):
        parent = by_id.get(control.parent_id or "")
        if parent is None or parent.kind != "LN0":
            issues.append(
                SemanticIssue(
                    "ERROR",
                    "SAMPLED_VALUE_CONTROL_REQUIRES_LN0",
                    "SampledValueControl 只能配置在 LLN0 下",
                    control,
                )
            )
        if not any(child.kind == "SMV_OPTS" for child in document.children(control.id)):
            issues.append(
                SemanticIssue(
                    "ERROR",
                    "SAMPLED_VALUE_CONTROL_SMV_OPTS_REQUIRED",
                    "SampledValueControl 必须包含 SmvOpts",
                    control,
                )
            )

    for fcda in (node for node in nodes if node.kind == "FCDA"):
        _validate_fcda(document, fcda, by_id, type_indexes, issues)

    for binding in (node for node in nodes if node.kind in {"GSE", "SMV"}):
        _validate_communication_binding(document, binding, by_id, issues)

    return issues


def _build_type_indexes(
    nodes: list[ModelNode],
    issues: list[SemanticIssue],
) -> dict[str, dict[str, ModelNode]]:
    indexes = {kind: {} for kind in ("LNODE_TYPE", "DO_TYPE", "DA_TYPE", "ENUM_TYPE")}
    for node in nodes:
        if node.kind not in indexes:
            continue
        type_id = str(node.attributes.get("id") or node.name)
        existing = indexes[node.kind].get(type_id)
        if existing is not None:
            issues.append(
                SemanticIssue(
                    "ERROR",
                    "TYPE_ID_DUPLICATE",
                    f"{node.kind} 类型 ID {type_id} 重复",
                    node,
                    "id",
                )
            )
            continue
        indexes[node.kind][type_id] = node
    return indexes


def _validate_logical_node_type(
    logical_node: ModelNode,
    lnode_types: dict[str, ModelNode],
    issues: list[SemanticIssue],
) -> None:
    type_id = str(logical_node.attributes.get("lnType") or "")
    lnode_type = lnode_types.get(type_id)
    if lnode_type is None:
        return
    actual_class = "LLN0" if logical_node.kind == "LN0" else str(logical_node.attributes.get("lnClass") or "")
    declared_class = str(lnode_type.attributes.get("lnClass") or "")
    if actual_class and declared_class and actual_class != declared_class:
        issues.append(
            SemanticIssue(
                "ERROR",
                "LNODE_TYPE_CLASS_MISMATCH",
                f"逻辑节点类 {actual_class} 与类型 {type_id} 声明的 {declared_class} 不一致",
                logical_node,
                "lnType",
            )
        )


def _validate_fcda(
    document: ModelDocument,
    fcda: ModelNode,
    by_id: dict[str, ModelNode],
    type_indexes: dict[str, dict[str, ModelNode]],
    issues: list[SemanticIssue],
) -> None:
    attrs = fcda.attributes
    owner_ln = _ancestor(fcda, by_id, {"LN0", "LN"})
    owner_ld = _ancestor(fcda, by_id, {"LDEVICE"})
    owner_ied = _ancestor(fcda, by_id, {"IED"})
    if owner_ln is None or owner_ld is None or owner_ied is None:
        issues.append(SemanticIssue("ERROR", "FCDA_CONTEXT_INVALID", "FCDA 不在有效的 IED/LDevice/LN 中", fcda))
        return

    target_ld_inst = str(attrs.get("ldInst") or owner_ld.attributes.get("inst") or owner_ld.name)
    target_ld = next(
        (
            node
            for node in document.nodes
            if node.kind == "LDEVICE"
            and _ancestor(node, by_id, {"IED"}) is owner_ied
            and str(node.attributes.get("inst") or node.name) == target_ld_inst
        ),
        None,
    )
    if target_ld is None:
        issues.append(
            SemanticIssue(
                "ERROR",
                "FCDA_LDEVICE_MISSING",
                f"FCDA 引用的逻辑设备 {target_ld_inst} 不存在于当前 IED",
                fcda,
                "ldInst",
            )
        )
        return

    target_ln = _find_logical_node(document, target_ld, attrs)
    if target_ln is None:
        ln_name = "".join(str(attrs.get(key) or "") for key in ("prefix", "lnClass", "lnInst"))
        issues.append(
            SemanticIssue(
                "ERROR",
                "FCDA_LOGICAL_NODE_MISSING",
                f"FCDA 引用的逻辑节点 {ln_name or '(空)'} 不存在于 {target_ld_inst}",
                fcda,
                "lnClass",
            )
        )
        return

    lnode_type_id = str(target_ln.attributes.get("lnType") or "")
    lnode_type = type_indexes["LNODE_TYPE"].get(lnode_type_id)
    if lnode_type is None:
        return

    do_name = str(attrs.get("doName") or "")
    do_type = _resolve_do_type(document, lnode_type, do_name, type_indexes["DO_TYPE"])
    if do_type is None:
        issues.append(
            SemanticIssue(
                "ERROR",
                "FCDA_DATA_OBJECT_MISSING",
                f"FCDA 引用的数据对象 {do_name or '(空)'} 不存在于类型 {lnode_type_id}",
                fcda,
                "doName",
            )
        )
        return

    functional_constraint = str(attrs.get("fc") or "")
    da_name = str(attrs.get("daName") or "")
    if not da_name:
        if functional_constraint and not _do_type_has_fc(document, do_type, functional_constraint, type_indexes):
            issues.append(
                SemanticIssue(
                    "ERROR",
                    "FCDA_FUNCTIONAL_CONSTRAINT_MISMATCH",
                    f"数据对象 {do_name} 中不存在 FC={functional_constraint} 的数据属性",
                    fcda,
                    "fc",
                )
            )
        return

    data_attribute = _resolve_data_attribute(document, do_type, da_name, type_indexes["DA_TYPE"])
    if data_attribute is None:
        issues.append(
            SemanticIssue(
                "ERROR",
                "FCDA_DATA_ATTRIBUTE_MISSING",
                f"FCDA 引用的数据属性 {do_name}.{da_name} 不存在",
                fcda,
                "daName",
            )
        )
        return
    declared_fc = str(data_attribute.attributes.get("fc") or "")
    if functional_constraint and declared_fc and functional_constraint != declared_fc:
        issues.append(
            SemanticIssue(
                "ERROR",
                "FCDA_FUNCTIONAL_CONSTRAINT_MISMATCH",
                f"数据属性 {do_name}.{da_name} 的 FC 为 {declared_fc}，不是 {functional_constraint}",
                fcda,
                "fc",
            )
        )


def _ancestor(
    node: ModelNode,
    by_id: dict[str, ModelNode],
    kinds: set[str],
) -> ModelNode | None:
    current = node
    while current.parent_id:
        current = by_id.get(current.parent_id)
        if current is None:
            return None
        if current.kind in kinds:
            return current
    return None


def _find_logical_node(
    document: ModelDocument,
    logical_device: ModelNode,
    attrs: dict,
) -> ModelNode | None:
    prefix = str(attrs.get("prefix") or "")
    ln_class = str(attrs.get("lnClass") or "")
    ln_inst = str(attrs.get("lnInst") or "")
    for node in document.children(logical_device.id):
        if node.kind == "LN0":
            if ln_class == "LLN0" and not prefix and not ln_inst:
                return node
            continue
        if node.kind != "LN":
            continue
        if (
            str(node.attributes.get("prefix") or "") == prefix
            and str(node.attributes.get("lnClass") or "") == ln_class
            and str(node.attributes.get("inst") or "") == ln_inst
        ):
            return node
    return None


def _resolve_do_type(
    document: ModelDocument,
    lnode_type: ModelNode,
    path: str,
    do_types: dict[str, ModelNode],
) -> ModelNode | None:
    segments = [segment for segment in path.split(".") if segment]
    if not segments:
        return None
    definition = next(
        (node for node in document.children(lnode_type.id) if node.kind == "DO_DEF" and node.name == segments[0]),
        None,
    )
    if definition is None:
        return None
    do_type = do_types.get(str(definition.attributes.get("type") or ""))
    for segment in segments[1:]:
        if do_type is None:
            return None
        nested = next(
            (node for node in document.children(do_type.id) if node.kind == "SDO_DEF" and node.name == segment),
            None,
        )
        if nested is None:
            return None
        do_type = do_types.get(str(nested.attributes.get("type") or ""))
    return do_type


def _resolve_data_attribute(
    document: ModelDocument,
    do_type: ModelNode,
    path: str,
    da_types: dict[str, ModelNode],
) -> ModelNode | None:
    segments = [segment for segment in path.split(".") if segment]
    if not segments:
        return None
    definition = next(
        (node for node in document.children(do_type.id) if node.kind == "DA_DEF" and node.name == segments[0]),
        None,
    )
    if definition is None:
        return None
    root_definition = definition
    current_type = da_types.get(str(definition.attributes.get("type") or ""))
    for segment in segments[1:]:
        if definition.attributes.get("bType") != "Struct" or current_type is None:
            return None
        definition = next(
            (node for node in document.children(current_type.id) if node.kind == "BDA_DEF" and node.name == segment),
            None,
        )
        if definition is None:
            return None
        current_type = da_types.get(str(definition.attributes.get("type") or ""))
    return root_definition


def _do_type_has_fc(
    document: ModelDocument,
    do_type: ModelNode,
    functional_constraint: str,
    type_indexes: dict[str, dict[str, ModelNode]],
) -> bool:
    for node in document.children(do_type.id):
        if node.kind == "DA_DEF" and str(node.attributes.get("fc") or "") == functional_constraint:
            return True
        if node.kind == "SDO_DEF":
            nested = type_indexes["DO_TYPE"].get(str(node.attributes.get("type") or ""))
            if nested is not None and _do_type_has_fc(document, nested, functional_constraint, type_indexes):
                return True
    return False


def _validate_communication_binding(
    document: ModelDocument,
    binding: ModelNode,
    by_id: dict[str, ModelNode],
    issues: list[SemanticIssue],
) -> None:
    connected_ap = _ancestor(binding, by_id, {"CONNECTED_AP"})
    if connected_ap is None:
        issues.append(
            SemanticIssue(
                "ERROR",
                "COMMUNICATION_BINDING_CONTEXT_INVALID",
                f"{binding.kind} 通信绑定不在 ConnectedAP 下",
                binding,
            )
        )
        return
    ied_name = str(connected_ap.attributes.get("iedName") or "")
    ap_name = str(connected_ap.attributes.get("apName") or "")
    ied = next((node for node in document.nodes if node.kind == "IED" and node.name == ied_name), None)
    if ied is None:
        return
    access_point = next(
        (node for node in document.children(ied.id) if node.kind == "ACCESS_POINT" and node.name == ap_name),
        None,
    )
    if access_point is None:
        issues.append(
            SemanticIssue(
                "ERROR",
                "CONNECTED_AP_ACCESS_POINT_MISSING",
                f"ConnectedAP 引用的访问点 {ied_name}/{ap_name} 不存在",
                connected_ap,
                "apName",
            )
        )
        return
    server = next((node for node in document.children(access_point.id) if node.kind == "SERVER"), None)
    ld_inst = str(binding.attributes.get("ldInst") or "")
    logical_device = (
        next(
            (
                node
                for node in document.children(server.id)
                if node.kind == "LDEVICE" and str(node.attributes.get("inst") or node.name) == ld_inst
            ),
            None,
        )
        if server is not None
        else None
    )
    if logical_device is None:
        issues.append(
            SemanticIssue(
                "ERROR",
                "COMMUNICATION_LDEVICE_MISSING",
                f"{binding.kind} 通信绑定引用的逻辑设备 {ld_inst or '(空)'} 不存在",
                binding,
                "ldInst",
            )
        )
        return
    ln0 = next((node for node in document.children(logical_device.id) if node.kind == "LN0"), None)
    control_kind = "GSE_CONTROL" if binding.kind == "GSE" else "SAMPLED_VALUE_CONTROL"
    cb_name = str(binding.attributes.get("cbName") or "")
    control = (
        next(
            (node for node in document.children(ln0.id) if node.kind == control_kind and node.name == cb_name),
            None,
        )
        if ln0 is not None
        else None
    )
    if control is None:
        element_name = "GSEControl" if binding.kind == "GSE" else "SampledValueControl"
        issues.append(
            SemanticIssue(
                "ERROR",
                "COMMUNICATION_CONTROL_BLOCK_MISSING",
                f"{binding.kind} 通信绑定引用的 {element_name} {ld_inst}/{cb_name or '(空)'} 不存在",
                binding,
                "cbName",
            )
        )
