"""Parameterized generators used by context-aware modeling templates."""

from __future__ import annotations

import re
from typing import Any

from src.modeling.document import ModelDocument, ModelNode

SCL_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{0,63}$")
INDEX_TOKEN = "{index}"


def preview_lnode_do_generation(
    document: ModelDocument,
    lnode_type: ModelNode,
    *,
    name_pattern: str,
    start_index: int,
    quantity: int,
    index_width: int,
    do_type_ref: str,
) -> dict[str, Any]:
    """Build a deterministic CREATE/KEEP/CONFLICT plan for indexed DOs."""

    if lnode_type.kind != "LNODE_TYPE":
        raise ValueError("参数化 DO 模板只能应用到 LNodeType")
    pattern = name_pattern.strip()
    if pattern.count(INDEX_TOKEN) != 1:
        raise ValueError("名称格式必须且只能包含一个 {index}")
    if start_index < 0:
        raise ValueError("起始序号不能小于 0")
    if quantity < 1 or quantity > 500:
        raise ValueError("一次最多生成 500 个 DO")
    if index_width < 1 or index_width > 8:
        raise ValueError("序号宽度必须在 1 到 8 之间")

    do_type = next(
        (
            node
            for node in document.nodes
            if node.kind == "DO_TYPE" and str(node.attributes.get("id") or node.name) == do_type_ref
        ),
        None,
    )
    if do_type is None:
        raise ValueError(f"DOType {do_type_ref or '（空）'} 不存在")

    existing = {child.name: child for child in document.children(lnode_type.id) if child.kind == "DO_DEF"}
    items: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for offset in range(quantity):
        index = start_index + offset
        name = pattern.replace(INDEX_TOKEN, f"{index:0{index_width}d}")
        if not SCL_NAME_PATTERN.fullmatch(name):
            raise ValueError(f"生成的名称 {name!r} 不符合 SCL 命名规则或超过 64 个字符")
        if name in seen_names:
            raise ValueError(f"名称格式产生了重复节点：{name}")
        seen_names.add(name)
        current = existing.get(name)
        current_type = str(current.attributes.get("type") or "") if current else ""
        if current is None:
            action = "CREATE"
            reason = ""
        elif current_type == do_type_ref:
            action = "KEEP"
            reason = "同名 DO 已引用相同 DOType"
        else:
            action = "CONFLICT"
            reason = f"同名 DO 已引用 {current_type or '未设置类型'}，不能改为 {do_type_ref}"
        items.append(
            {
                "name": name,
                "index": index,
                "action": action,
                "reason": reason,
                "existing_node_id": current.id if current else None,
                "attributes": {"type": do_type_ref},
            }
        )

    counts = {action: sum(item["action"] == action for item in items) for action in ("CREATE", "KEEP", "CONFLICT")}
    return {
        "target": {
            "id": lnode_type.id,
            "name": lnode_type.name,
            "lnClass": str(lnode_type.attributes.get("lnClass") or ""),
            "revision": lnode_type.revision,
        },
        "do_type": {
            "id": do_type_ref,
            "name": do_type.name,
            "cdc": str(do_type.attributes.get("cdc") or ""),
            "description": str(do_type.attributes.get("desc") or ""),
        },
        "parameters": {
            "name_pattern": pattern,
            "start_index": start_index,
            "quantity": quantity,
            "index_width": index_width,
            "do_type_ref": do_type_ref,
        },
        "items": items,
        "summary": {
            "total": len(items),
            "create": counts["CREATE"],
            "keep": counts["KEEP"],
            "conflict": counts["CONFLICT"],
        },
    }
