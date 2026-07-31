"""In-memory aggregate for an editable IEC 61850 model."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
import hashlib
from io import StringIO
import json
from typing import Any
import uuid


def _compact_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(slots=True)
class ModelNode:
    id: str
    project_id: str
    parent_id: str | None
    kind: str
    name: str
    sort_order: int = 0
    attributes: dict[str, Any] = field(default_factory=dict)
    revision: int = 1
    created_at: None = None
    updated_at: None = None

    @property
    def attributes_json(self) -> str:
        return _compact_json(self.attributes)

    @attributes_json.setter
    def attributes_json(self, value: str) -> None:
        parsed = json.loads(value or "{}")
        self.attributes = parsed if isinstance(parsed, dict) else {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "kind": self.kind,
            "name": self.name,
            "sort_order": self.sort_order,
            "attributes": self.attributes,
            "revision": self.revision,
        }


@dataclass(slots=True)
class ModelReference:
    id: str
    source_node_id: str
    target_node_id: str
    relation_type: str
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def attributes_json(self) -> str:
        return _compact_json(self.attributes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "relation_type": self.relation_type,
            "attributes": self.attributes,
        }


class ModelDocument:
    FORMAT_VERSION = 1

    def __init__(
        self,
        project_id: str,
        nodes: Iterable[ModelNode] = (),
        references: Iterable[ModelReference] = (),
    ) -> None:
        self.project_id = project_id
        self.nodes = list(nodes)
        self.references = list(references)
        self._reindex()

    @classmethod
    def empty(cls, project_id: str) -> ModelDocument:
        return cls(project_id)

    @classmethod
    def from_json(cls, project_id: str, content: str | None) -> ModelDocument:
        if not content:
            return cls.empty(project_id)
        payload = json.loads(content)
        if payload.get("format_version") != cls.FORMAT_VERSION:
            raise ValueError(f"Unsupported model document version: {payload.get('format_version')}")
        nodes = [
            ModelNode(
                id=item["id"],
                project_id=project_id,
                parent_id=item.get("parent_id"),
                kind=item["kind"],
                name=item["name"],
                sort_order=int(item.get("sort_order", 0)),
                attributes=dict(item.get("attributes") or {}),
                revision=int(item.get("revision", 1)),
            )
            for item in payload.get("nodes", [])
        ]
        references = [
            ModelReference(
                id=item["id"],
                source_node_id=item["source_node_id"],
                target_node_id=item["target_node_id"],
                relation_type=item["relation_type"],
                attributes=dict(item.get("attributes") or {}),
            )
            for item in payload.get("references", [])
        ]
        return cls(project_id, nodes, references)

    def _reindex(self) -> None:
        self.by_id = {node.id: node for node in self.nodes}
        self.by_parent: dict[str | None, list[ModelNode]] = defaultdict(list)
        for node in self.nodes:
            self.by_parent[node.parent_id].append(node)
        for children in self.by_parent.values():
            children.sort(key=lambda item: (item.sort_order, item.name))

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.FORMAT_VERSION,
            "nodes": [node.to_dict() for node in self.nodes],
            "references": [reference.to_dict() for reference in self.references],
        }

    def to_json(self) -> str:
        # 逐项写入，避免大模型序列化时先构造完整 nodes/references 字典列表。
        buffer = StringIO()
        buffer.write(f'{{"format_version":{self.FORMAT_VERSION},"nodes":[')
        for index, node in enumerate(self.nodes):
            if index:
                buffer.write(",")
            buffer.write(_compact_json(node.to_dict()))
        buffer.write('],"references":[')
        for index, reference in enumerate(self.references):
            if index:
                buffer.write(",")
            buffer.write(_compact_json(reference.to_dict()))
        buffer.write("]}")
        return buffer.getvalue()

    def checksum(self, content: str | None = None) -> str:
        serialized = content if content is not None else self.to_json()
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, node_id: str) -> ModelNode | None:
        return self.by_id.get(node_id)

    def children(self, parent_id: str | None) -> list[ModelNode]:
        return self.by_parent.get(parent_id, [])

    def add_node(
        self,
        *,
        kind: str,
        name: str,
        parent_id: str | None,
        attributes: dict[str, Any] | None = None,
        sort_order: int = 0,
        node_id: str | None = None,
        revision: int = 1,
    ) -> ModelNode:
        node = ModelNode(
            id=node_id or str(uuid.uuid4()),
            project_id=self.project_id,
            parent_id=parent_id,
            kind=kind,
            name=name,
            sort_order=sort_order,
            attributes=dict(attributes or {}),
            revision=revision,
        )
        self.nodes.append(node)
        self.by_id[node.id] = node
        self.by_parent[node.parent_id].append(node)
        return node

    def subtree_ids(self, node_id: str) -> list[str]:
        result: list[str] = []
        stack = [node_id]
        while stack:
            current = stack.pop()
            result.append(current)
            stack.extend(child.id for child in self.children(current))
        return result

    def node_path(self, node: ModelNode) -> str:
        names = [node.name]
        parent_id = node.parent_id
        while parent_id:
            parent = self.get(parent_id)
            if parent is None:
                break
            names.append(parent.name)
            parent_id = parent.parent_id
        return "/".join(reversed(names))

    def remove_subtree(self, node_id: str) -> int:
        removed = set(self.subtree_ids(node_id))
        self.nodes = [node for node in self.nodes if node.id not in removed]
        self.references = [
            reference
            for reference in self.references
            if reference.source_node_id not in removed and reference.target_node_id not in removed
        ]
        self._reindex()
        return len(removed)

    def rebuild_references(self) -> int:
        type_indexes: dict[str, dict[str, ModelNode]] = {
            kind: {} for kind in ("LNODE_TYPE", "DO_TYPE", "DA_TYPE", "ENUM_TYPE")
        }
        ieds: dict[str, ModelNode] = {}
        for node in self.nodes:
            if node.kind in type_indexes:
                type_indexes[node.kind][str(node.attributes.get("id") or node.name)] = node
            elif node.kind == "IED":
                ieds[node.name] = node

        references: list[ModelReference] = []

        def add(source: ModelNode, target: ModelNode | None, relation: str, external: str) -> None:
            if target is not None:
                references.append(
                    ModelReference(
                        id=str(uuid.uuid4()),
                        source_node_id=source.id,
                        target_node_id=target.id,
                        relation_type=relation,
                        attributes={"external_ref": external},
                    )
                )

        for node in self.nodes:
            attrs = node.attributes
            if node.kind in ("LN0", "LN") and attrs.get("lnType"):
                ref = str(attrs["lnType"])
                add(node, type_indexes["LNODE_TYPE"].get(ref), "LN_TYPE", ref)
            elif node.kind in ("DO_DEF", "SDO_DEF") and attrs.get("type"):
                ref = str(attrs["type"])
                add(node, type_indexes["DO_TYPE"].get(ref), "DO_TYPE", ref)
            elif node.kind in ("DA_DEF", "BDA_DEF") and attrs.get("type"):
                ref = str(attrs["type"])
                target_kind = "DA_TYPE" if attrs.get("bType") == "Struct" else "ENUM_TYPE"
                add(node, type_indexes[target_kind].get(ref), target_kind, ref)
            elif node.kind in ("REPORT_CONTROL", "GSE_CONTROL", "SAMPLED_VALUE_CONTROL") and attrs.get("datSet"):
                ref = str(attrs["datSet"])
                target = next(
                    (item for item in self.children(node.parent_id) if item.kind == "DATASET" and item.name == ref),
                    None,
                )
                add(node, target, "CONTROL_DATASET", ref)
            elif node.kind == "CONNECTED_AP" and attrs.get("iedName"):
                ref = str(attrs["iedName"])
                add(node, ieds.get(ref), "CONNECTED_AP_IED", ref)

        self.references = references
        return len(references)
