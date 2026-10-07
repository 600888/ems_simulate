"""Bounded recursive discovery, independent of SDK and persistence."""

import asyncio
from collections import deque


async def discover_variables(
    node_id,
    children,
    inspect,
    *,
    max_depth=16,
    max_nodes=1000,
    timeout_s=30,
    include_standard=False,
):
    if not 1 <= max_depth <= 64 or not 1 <= max_nodes <= 1000 or not 1 <= timeout_s <= 60:
        raise ValueError("自动发现参数超出范围")

    def canonical(value):
        return value.removeprefix("ns=0;")

    root = canonical(node_id)
    pending = deque([(root, 0)])
    seen = {root}
    result = {"nodes": [], "visited": 0, "errors": [], "truncated": False, "reason": None}

    def truncate(reason):
        result["truncated"] = True
        result["reason"] = result["reason"] or reason

    try:
        async with asyncio.timeout(timeout_s):
            while pending:
                current, depth = pending.popleft()
                result["visited"] += 1
                try:
                    node = await inspect(current)
                    if node["node_class"] == "Variable" and node.get("readable"):
                        standard = node.get("namespace_index", 0) == 0
                        if include_standard or not standard:
                            result["nodes"].append(node)
                            if len(result["nodes"]) >= max_nodes:
                                truncate("max_nodes")
                                break
                    if node["node_class"] not in {"Object", "Variable", "View"}:
                        continue
                    child_ids = await children(current)
                    for child in child_ids:
                        key = canonical(child)
                        # Avoid the standard Server diagnostics subtree by default.
                        if not include_standard and key == "i=2253" and key != root:
                            continue
                        if key in seen:
                            continue
                        if depth >= max_depth:
                            truncate("max_depth")
                            continue
                        if len(seen) >= 10000:
                            truncate("max_visited")
                            continue
                        seen.add(key)
                        pending.append((key, depth + 1))
                except Exception as exc:
                    if current == root:
                        raise
                    if len(result["errors"]) < 100:
                        result["errors"].append({"node_id": current, "message": str(exc)})
    except TimeoutError:
        truncate("timeout")
    return result
