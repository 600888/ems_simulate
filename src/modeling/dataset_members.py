"""DataSet member discovery helpers for the editable IEC 61850 model."""

from __future__ import annotations

from collections.abc import Iterable
import json
from typing import Any

from src.modeling.document import ModelDocument, ModelNode
from src.modeling.semantic_validation import validate_semantic_references


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


def _candidate_id(attributes: dict[str, Any]) -> str:
    return json.dumps(
        [str(attributes.get(key) or "") for key in ("ldInst", "prefix", "lnClass", "lnInst", "doName", "daName", "fc")],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _logical_node_name(node: ModelNode) -> str:
    if node.kind == "LN0":
        return "LLN0"
    return "".join(str(node.attributes.get(key) or "") for key in ("prefix", "lnClass", "inst"))


def _walk_data_attributes(
    document: ModelDocument,
    definition: ModelNode,
    da_types: dict[str, ModelNode],
    *,
    path: str,
    inherited_fc: str,
) -> Iterable[tuple[str, str, str, str]]:
    """Yield ``(path, fc, bType, description)`` for leaf data attributes."""

    attributes = definition.attributes
    fc = str(attributes.get("fc") or inherited_fc)
    b_type = str(attributes.get("bType") or "")
    description = str(attributes.get("desc") or "")
    if b_type != "Struct":
        yield path, fc, b_type, description
        return

    da_type = da_types.get(str(attributes.get("type") or ""))
    if da_type is None:
        return
    for child in document.children(da_type.id):
        if child.kind != "BDA_DEF":
            continue
        child_path = f"{path}.{child.name}" if path else child.name
        yield from _walk_data_attributes(
            document,
            child,
            da_types,
            path=child_path,
            inherited_fc=fc,
        )


def _walk_data_objects(
    document: ModelDocument,
    do_type: ModelNode,
    do_types: dict[str, ModelNode],
    da_types: dict[str, ModelNode],
    *,
    path: str,
) -> Iterable[tuple[str, str, str, str, str]]:
    """Yield ``(doName, daName, fc, bType, description)`` leaf targets."""

    for child in document.children(do_type.id):
        if child.kind == "DA_DEF":
            for da_path, fc, b_type, description in _walk_data_attributes(
                document,
                child,
                da_types,
                path=child.name,
                inherited_fc=str(child.attributes.get("fc") or ""),
            ):
                yield path, da_path, fc, b_type, description
        elif child.kind == "SDO_DEF":
            nested_type = do_types.get(str(child.attributes.get("type") or ""))
            if nested_type is None:
                continue
            nested_path = f"{path}.{child.name}" if path else child.name
            yield from _walk_data_objects(
                document,
                nested_type,
                do_types,
                da_types,
                path=nested_path,
            )


def list_dataset_member_candidates(
    document: ModelDocument,
    dataset: ModelNode,
) -> dict[str, Any]:
    """Build leaf-FCDA candidates and report the status of existing members."""

    if dataset.kind != "DATASET":
        raise ValueError("DataSet member candidates require a DATASET node")

    by_id = {node.id: node for node in document.nodes}
    owner_ied = _ancestor(dataset, by_id, {"IED"})
    if owner_ied is None:
        raise ValueError("DataSet is not inside an IED")

    lnode_types = {
        str(node.attributes.get("id") or node.name): node for node in document.nodes if node.kind == "LNODE_TYPE"
    }
    do_types = {str(node.attributes.get("id") or node.name): node for node in document.nodes if node.kind == "DO_TYPE"}
    da_types = {str(node.attributes.get("id") or node.name): node for node in document.nodes if node.kind == "DA_TYPE"}

    existing_members = [child for child in document.children(dataset.id) if child.kind == "FCDA"]
    existing_by_key = {_candidate_id(member.attributes): member for member in existing_members}
    candidates: list[dict[str, Any]] = []

    logical_devices = [
        node for node in document.nodes if node.kind == "LDEVICE" and _ancestor(node, by_id, {"IED"}) is owner_ied
    ]
    logical_devices.sort(key=lambda node: (node.sort_order, node.name))
    for logical_device in logical_devices:
        ld_inst = str(logical_device.attributes.get("inst") or logical_device.name)
        logical_nodes = [node for node in document.children(logical_device.id) if node.kind in {"LN0", "LN"}]
        for logical_node in logical_nodes:
            lnode_type = lnode_types.get(str(logical_node.attributes.get("lnType") or ""))
            if lnode_type is None:
                continue
            prefix = "" if logical_node.kind == "LN0" else str(logical_node.attributes.get("prefix") or "")
            ln_class = "LLN0" if logical_node.kind == "LN0" else str(logical_node.attributes.get("lnClass") or "")
            ln_inst = "" if logical_node.kind == "LN0" else str(logical_node.attributes.get("inst") or "")
            logical_node_name = _logical_node_name(logical_node)
            for do_definition in document.children(lnode_type.id):
                if do_definition.kind != "DO_DEF":
                    continue
                do_type = do_types.get(str(do_definition.attributes.get("type") or ""))
                if do_type is None:
                    continue
                leaf_targets = list(
                    _walk_data_objects(
                        document,
                        do_type,
                        do_types,
                        da_types,
                        path=do_definition.name,
                    )
                )
                data_object_description = str(do_definition.attributes.get("desc") or "")
                for do_name, fc in sorted(
                    {(target_do_name, target_fc) for target_do_name, _, target_fc, _, _ in leaf_targets if target_fc}
                ):
                    attributes = {
                        "ldInst": ld_inst,
                        "prefix": prefix,
                        "lnClass": ln_class,
                        "lnInst": ln_inst,
                        "doName": do_name,
                        "daName": "",
                        "fc": fc,
                    }
                    candidate_id = _candidate_id(attributes)
                    reference = f"{ld_inst}/{logical_node_name}.{do_name}"
                    existing = existing_by_key.get(candidate_id)
                    candidates.append(
                        {
                            "id": candidate_id,
                            "reference": reference,
                            "logical_device": ld_inst,
                            "logical_node": logical_node_name,
                            "data_object": do_name,
                            "data_attribute": "",
                            "fc": fc,
                            "b_type": str(do_type.attributes.get("cdc") or ""),
                            "description": data_object_description,
                            "group_key": (f"{ld_inst}/{logical_node_name}.{do_name}"),
                            "selection_level": "DO",
                            "is_companion": False,
                            "existing": existing is not None,
                            "existing_node_id": existing.id if existing else None,
                            "attributes": attributes,
                        }
                    )
                for do_name, da_name, fc, b_type, description in leaf_targets:
                    attributes = {
                        "ldInst": ld_inst,
                        "prefix": prefix,
                        "lnClass": ln_class,
                        "lnInst": ln_inst,
                        "doName": do_name,
                        "daName": da_name,
                        "fc": fc,
                    }
                    candidate_id = _candidate_id(attributes)
                    reference = f"{ld_inst}/{logical_node_name}.{do_name}.{da_name}"
                    existing = existing_by_key.get(candidate_id)
                    candidates.append(
                        {
                            "id": candidate_id,
                            "reference": reference,
                            "logical_device": ld_inst,
                            "logical_node": logical_node_name,
                            "data_object": do_name,
                            "data_attribute": da_name,
                            "fc": fc,
                            "b_type": b_type,
                            "description": description or data_object_description,
                            "group_key": (f"{ld_inst}/{logical_node_name}.{do_name}"),
                            "selection_level": "DA",
                            "is_companion": da_name.rsplit(".", 1)[-1] in {"q", "t"},
                            "existing": existing is not None,
                            "existing_node_id": existing.id if existing else None,
                            "attributes": attributes,
                        }
                    )

    candidates.sort(
        key=lambda item: (
            item["logical_device"],
            item["logical_node"],
            item["data_object"],
            item["selection_level"],
            item["data_attribute"],
            item["fc"],
        )
    )
    candidate_ids = {item["id"] for item in candidates}
    semantic_issues = validate_semantic_references(document)
    issues_by_node: dict[str, list[str]] = {}
    for issue in semantic_issues:
        if issue.node.kind == "FCDA" and issue.code.startswith("FCDA_"):
            issues_by_node.setdefault(issue.node.id, []).append(issue.message)

    existing_payload = []
    for member in existing_members:
        candidate_id = _candidate_id(member.attributes)
        member_issues = issues_by_node.get(member.id, [])
        valid = not member_issues
        existing_payload.append(
            {
                "node_id": member.id,
                "name": member.name,
                "reference": _format_reference(member.attributes),
                "candidate_id": (candidate_id if candidate_id in candidate_ids else None),
                "valid": valid,
                "reason": (
                    "；".join(member_issues)
                    if member_issues
                    else ("" if candidate_id in candidate_ids else "当前模型中没有可匹配的候选项")
                ),
                "attributes": dict(member.attributes),
                "sort_order": member.sort_order,
            }
        )
    existing_payload.sort(key=lambda item: (item["sort_order"], item["name"]))
    return {
        "dataset": {
            "id": dataset.id,
            "name": dataset.name,
            "path": document.node_path(dataset),
            "revision": dataset.revision,
        },
        "candidates": candidates,
        "existing_members": existing_payload,
        "summary": {
            "candidate_count": len(candidates),
            "existing_count": len(existing_members),
            "invalid_count": sum(1 for member in existing_payload if not member["valid"]),
        },
    }


def candidate_attributes(
    document: ModelDocument,
    dataset: ModelNode,
    candidate_id: str,
) -> dict[str, Any] | None:
    candidates = list_dataset_member_candidates(document, dataset)["candidates"]
    candidate = next(
        (item for item in candidates if item["id"] == candidate_id),
        None,
    )
    return dict(candidate["attributes"]) if candidate else None


def _format_reference(attributes: dict[str, Any]) -> str:
    ld_inst = str(attributes.get("ldInst") or "")
    logical_node = "".join(str(attributes.get(key) or "") for key in ("prefix", "lnClass", "lnInst"))
    data_path = ".".join(
        value
        for value in (
            str(attributes.get("doName") or ""),
            str(attributes.get("daName") or ""),
        )
        if value
    )
    return f"{ld_inst}/{logical_node}.{data_path}".rstrip(".")
