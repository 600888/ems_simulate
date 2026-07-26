"""Resolve an LN's effective data model without materializing SCL instance nodes."""

from __future__ import annotations

import hashlib
from typing import Any

from src.modeling.catalog import KIND_LABELS
from src.modeling.document import ModelDocument, ModelNode


def _type_index(document: ModelDocument, kind: str) -> dict[str, ModelNode]:
    return {str(node.attributes.get("id") or node.name): node for node in document.nodes if node.kind == kind}


def _virtual_id(logical_node_id: str, path: str, kind: str) -> str:
    digest = hashlib.sha1(
        f"{logical_node_id}|{kind}|{path}".encode(),
        usedforsecurity=False,
    ).hexdigest()[:20]
    return f"effective:{digest}"


def _actual_payload(
    node: ModelNode,
    *,
    source: ModelNode | None = None,
    template_path: str = "",
) -> dict[str, Any]:
    return {
        "id": node.id,
        "project_id": node.project_id,
        "parent_id": node.parent_id,
        "kind": node.kind,
        "kind_label": KIND_LABELS.get(node.kind, node.kind),
        "name": node.name,
        "label": node.name,
        "sort_order": node.sort_order,
        "attributes": dict(node.attributes),
        "revision": node.revision,
        "child_count": 0,
        "protected": bool(node.attributes.get("_templateInherited")),
        "detail_loaded": True,
        "virtual": False,
        "inherited": source is not None,
        "instance_override": source is not None,
        "source_node_id": source.id if source else None,
        "source_kind": source.kind if source else "",
        "template_path": template_path,
    }


def _virtual_payload(
    logical_node: ModelNode,
    *,
    parent_id: str,
    kind: str,
    definition: ModelNode,
    template_path: str,
) -> dict[str, Any]:
    return {
        "id": _virtual_id(logical_node.id, template_path, kind),
        "project_id": logical_node.project_id,
        "parent_id": parent_id,
        "kind": kind,
        "kind_label": KIND_LABELS.get(kind, kind),
        "name": definition.name,
        "label": definition.name,
        "sort_order": definition.sort_order,
        "attributes": dict(definition.attributes),
        "revision": 0,
        "child_count": 0,
        "protected": True,
        "detail_loaded": True,
        "virtual": True,
        "inherited": True,
        "instance_override": False,
        "source_node_id": definition.id,
        "source_kind": definition.kind,
        "template_path": template_path,
    }


def _plain_instance_subtree(
    document: ModelDocument,
    node: ModelNode,
) -> dict[str, Any]:
    payload = _actual_payload(node)
    children = [
        _plain_instance_subtree(document, child)
        for child in document.children(node.id)
        if not child.attributes.get("_templateInherited")
    ]
    payload["children"] = children
    payload["child_count"] = len(children)
    return payload


def build_effective_instance_tree(
    document: ModelDocument,
    logical_node: ModelNode,
) -> dict[str, Any]:
    """Return type-inherited DOI/SDI/DAI nodes overlaid with real overrides."""

    if logical_node.kind not in {"LN0", "LN"}:
        raise ValueError("Effective data model can only be resolved for LN0 or LN")

    lnode_types = _type_index(document, "LNODE_TYPE")
    do_types = _type_index(document, "DO_TYPE")
    da_types = _type_index(document, "DA_TYPE")
    ln_type_id = str(logical_node.attributes.get("lnType") or "")
    ln_type = lnode_types.get(ln_type_id)
    warnings: list[dict[str, str]] = []
    if ln_type is None:
        return {
            "logical_node_id": logical_node.id,
            "ln_type": ln_type_id,
            "resolved": False,
            "nodes": [],
            "warnings": [
                {
                    "code": "LNODE_TYPE_MISSING",
                    "path": "",
                    "message": f"逻辑节点类型 {ln_type_id or '（空）'} 不存在",
                }
            ],
            "summary": {"data_objects": 0, "data_attributes": 0, "overrides": 0},
        }

    root_instances = {
        child.name: child
        for child in document.children(logical_node.id)
        if child.kind == "DOI" and not child.attributes.get("_templateInherited")
    }
    used_root_instances: set[str] = set()
    data_object_count = 0
    data_attribute_count = 0
    override_count = 0

    def instance_children(parent: ModelNode | None) -> dict[str, ModelNode]:
        if parent is None:
            return {}
        return {
            child.name: child
            for child in document.children(parent.id)
            if child.kind in {"DAI", "SDI"} and not child.attributes.get("_templateInherited")
        }

    def attach_children(
        payload: dict[str, Any],
        children: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload["children"] = children
        payload["child_count"] = len(children)
        return payload

    def resolve_da_type(
        definition: ModelNode,
        *,
        parent_payload: dict[str, Any],
        actual_parent: ModelNode | None,
        template_path: str,
        inherited_fc: str,
        active_types: frozenset[str],
    ) -> list[dict[str, Any]]:
        nonlocal data_attribute_count, override_count
        type_id = str(definition.attributes.get("type") or "")
        da_type = da_types.get(type_id)
        if da_type is None:
            warnings.append(
                {
                    "code": "DA_TYPE_MISSING",
                    "path": template_path,
                    "message": f"结构化数据属性引用的 DAType {type_id or '（空）'} 不存在",
                }
            )
            return []
        active_key = f"DA_TYPE:{type_id}"
        if active_key in active_types:
            warnings.append(
                {
                    "code": "TYPE_CYCLE",
                    "path": template_path,
                    "message": f"检测到 DAType 循环引用：{type_id}",
                }
            )
            return []
        actual_by_name = instance_children(actual_parent)
        children: list[dict[str, Any]] = []
        used: set[str] = set()
        next_active = active_types | {active_key}
        for child_definition in document.children(da_type.id):
            if child_definition.kind != "BDA_DEF":
                continue
            child_path = f"{template_path}.{child_definition.name}"
            actual = actual_by_name.get(child_definition.name)
            if actual:
                used.add(actual.id)
                override_count += 1
            is_struct = str(child_definition.attributes.get("bType") or "") == "Struct"
            kind = "SDI" if is_struct else "DAI"
            payload = (
                _actual_payload(
                    actual,
                    source=child_definition,
                    template_path=child_path,
                )
                if actual
                else _virtual_payload(
                    logical_node,
                    parent_id=parent_payload["id"],
                    kind=kind,
                    definition=child_definition,
                    template_path=child_path,
                )
            )
            payload["effective_fc"] = str(child_definition.attributes.get("fc") or inherited_fc)
            data_attribute_count += 1
            nested = (
                resolve_da_type(
                    child_definition,
                    parent_payload=payload,
                    actual_parent=actual,
                    template_path=child_path,
                    inherited_fc=payload["effective_fc"],
                    active_types=next_active,
                )
                if is_struct
                else []
            )
            children.append(attach_children(payload, nested))
        for actual in actual_by_name.values():
            if actual.id not in used:
                children.append(_plain_instance_subtree(document, actual))
        return children

    def resolve_do_type(
        do_type: ModelNode,
        *,
        parent_payload: dict[str, Any],
        actual_parent: ModelNode | None,
        template_path: str,
        active_types: frozenset[str],
    ) -> list[dict[str, Any]]:
        nonlocal data_attribute_count, override_count
        type_id = str(do_type.attributes.get("id") or do_type.name)
        active_key = f"DO_TYPE:{type_id}"
        if active_key in active_types:
            warnings.append(
                {
                    "code": "TYPE_CYCLE",
                    "path": template_path,
                    "message": f"检测到 DOType 循环引用：{type_id}",
                }
            )
            return []
        actual_by_name = instance_children(actual_parent)
        children: list[dict[str, Any]] = []
        used: set[str] = set()
        next_active = active_types | {active_key}
        for definition in document.children(do_type.id):
            if definition.kind not in {"DA_DEF", "SDO_DEF"}:
                continue
            child_path = f"{template_path}.{definition.name}"
            actual = actual_by_name.get(definition.name)
            if actual:
                used.add(actual.id)
                override_count += 1
            is_sdo = definition.kind == "SDO_DEF"
            is_struct = definition.kind == "DA_DEF" and str(definition.attributes.get("bType") or "") == "Struct"
            kind = "SDI" if is_sdo or is_struct else "DAI"
            payload = (
                _actual_payload(
                    actual,
                    source=definition,
                    template_path=child_path,
                )
                if actual
                else _virtual_payload(
                    logical_node,
                    parent_id=parent_payload["id"],
                    kind=kind,
                    definition=definition,
                    template_path=child_path,
                )
            )
            payload["effective_fc"] = str(definition.attributes.get("fc") or "")
            data_attribute_count += 1
            nested: list[dict[str, Any]] = []
            if is_sdo:
                nested_type_id = str(definition.attributes.get("type") or "")
                nested_type = do_types.get(nested_type_id)
                if nested_type is None:
                    warnings.append(
                        {
                            "code": "DO_TYPE_MISSING",
                            "path": child_path,
                            "message": f"子数据对象引用的 DOType {nested_type_id or '（空）'} 不存在",
                        }
                    )
                else:
                    nested = resolve_do_type(
                        nested_type,
                        parent_payload=payload,
                        actual_parent=actual,
                        template_path=child_path,
                        active_types=next_active,
                    )
            elif is_struct:
                nested = resolve_da_type(
                    definition,
                    parent_payload=payload,
                    actual_parent=actual,
                    template_path=child_path,
                    inherited_fc=payload["effective_fc"],
                    active_types=next_active,
                )
            children.append(attach_children(payload, nested))
        for actual in actual_by_name.values():
            if actual.id not in used:
                children.append(_plain_instance_subtree(document, actual))
        return children

    roots: list[dict[str, Any]] = []
    for definition in document.children(ln_type.id):
        if definition.kind != "DO_DEF":
            continue
        data_object_count += 1
        template_path = definition.name
        actual = root_instances.get(definition.name)
        if actual:
            used_root_instances.add(actual.id)
            override_count += 1
            payload = _actual_payload(
                actual,
                source=definition,
                template_path=template_path,
            )
        else:
            payload = _virtual_payload(
                logical_node,
                parent_id=logical_node.id,
                kind="DOI",
                definition=definition,
                template_path=template_path,
            )
        type_id = str(definition.attributes.get("type") or "")
        do_type = do_types.get(type_id)
        if do_type is None:
            warnings.append(
                {
                    "code": "DO_TYPE_MISSING",
                    "path": template_path,
                    "message": f"数据对象引用的 DOType {type_id or '（空）'} 不存在",
                }
            )
            children: list[dict[str, Any]] = []
        else:
            payload["cdc"] = str(do_type.attributes.get("cdc") or "")
            children = resolve_do_type(
                do_type,
                parent_payload=payload,
                actual_parent=actual,
                template_path=template_path,
                active_types=frozenset(),
            )
        roots.append(attach_children(payload, children))

    for actual in root_instances.values():
        if actual.id not in used_root_instances:
            roots.append(_plain_instance_subtree(document, actual))

    stack = [*roots]
    while stack:
        node = stack.pop()
        node["logical_node_id"] = logical_node.id
        stack.extend(node.get("children") or [])

    return {
        "logical_node_id": logical_node.id,
        "ln_type": ln_type_id,
        "ln_type_node_id": ln_type.id,
        "resolved": True,
        "nodes": roots,
        "warnings": warnings,
        "summary": {
            "data_objects": data_object_count,
            "data_attributes": data_attribute_count,
            "overrides": override_count,
        },
    }
