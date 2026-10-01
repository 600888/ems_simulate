"""Transactional persistence of the scalar NodeSet model, separate from point metadata."""

import asyncio
from typing import Any

from sqlalchemy import select

from src.data.controller.db import local_session
from src.data.model.channel import Channel
from src.data.model.opcua_config import OpcUaConfig
from src.data.model.opcua_node import OpcUaNode
from src.data.model.opcua_point import OpcUaPoint
from src.proto.opcua.core.nodeset import ScalarNodeSet, inspect_nodeset


def _inspect(session, channel_id: int, model: ScalarNodeSet) -> dict[str, Any]:
    channel = session.get(Channel, channel_id)
    if channel is None or channel.protocol_type != 7 or channel.conn_type != 2:
        raise ValueError("OPC UA 服务端通道不存在")
    config = session.get(OpcUaConfig, channel_id)
    nodes = session.scalars(select(OpcUaNode).where(OpcUaNode.channel_id == channel_id)).all()
    existing = {node.node_id: node for node in nodes}
    point_nodes = set(session.scalars(select(OpcUaPoint.node_id).where(OpcUaPoint.channel_id == channel_id)))
    errors: list[dict[str, str]] = []
    conflicts: list[dict[str, str]] = []
    uris = {node.namespace_uri for node in nodes}
    if (config and config.namespace_uri and config.namespace_uri != model.namespace_uri) or (
        uris and uris != {model.namespace_uri}
    ):
        errors.append({"node_id": "*", "message": "模型命名空间 URI 与现有配置或节点不一致"})
    for definition in model.definitions:
        node_id = definition["node_id"]
        if node_id in point_nodes:
            errors.append({"node_id": node_id, "message": "节点属于 Excel 点表，请通过点表覆盖更新"})
        elif node_id in existing:
            conflicts.append({"node_id": node_id, "message": "节点定义已存在"})
    return {
        "sha256": model.sha256,
        "namespace_uri": model.namespace_uri,
        "total": len(model.definitions),
        "errors": errors,
        "conflicts": conflicts,
    }


class OpcUaModelService:
    @staticmethod
    async def preview_upload(channel_id: int, content: bytes) -> dict[str, Any]:
        model = await inspect_nodeset(content)
        return await asyncio.to_thread(OpcUaModelService.preview, channel_id, model)

    @staticmethod
    async def apply_upload(channel_id: int, content: bytes, expected_sha256: str, mode: str) -> dict[str, Any]:
        model = await inspect_nodeset(content)
        return await asyncio.to_thread(OpcUaModelService.apply, channel_id, model, expected_sha256, mode)

    @staticmethod
    def preview(channel_id: int, model: ScalarNodeSet) -> dict[str, Any]:
        with local_session() as session:
            return _inspect(session, channel_id, model)

    @staticmethod
    def apply(channel_id: int, model: ScalarNodeSet, expected_sha256: str, mode: str) -> dict[str, Any]:
        if model.sha256 != expected_sha256:
            raise ValueError("模型内容与预检时不一致，请重新预检")
        if mode not in {"add", "overwrite"}:
            raise ValueError("冲突策略必须为 add 或 overwrite")
        with local_session() as session, session.begin():
            inspection = _inspect(session, channel_id, model)
            if inspection["errors"]:
                raise ValueError(inspection["errors"][0]["message"])
            if mode == "add" and inspection["conflicts"]:
                raise ValueError("模型与现有节点冲突，请选择覆盖策略")
            nodes = session.scalars(select(OpcUaNode).where(OpcUaNode.channel_id == channel_id)).all()
            by_node = {node.node_id: node for node in nodes}
            config = session.get(OpcUaConfig, channel_id)
            if config is None:
                config = OpcUaConfig(channel_id=channel_id, namespace_uri=model.namespace_uri)
                session.add(config)
            elif not config.namespace_uri:
                config.namespace_uri = model.namespace_uri
            created = updated = 0
            for definition in model.definitions:
                record = by_node.get(definition["node_id"])
                if record is None:
                    session.add(OpcUaNode(channel_id=channel_id, **definition))
                    created += 1
                else:
                    for field, value in definition.items():
                        setattr(record, field, value)
                    updated += 1
        return {
            "created": created,
            "updated": updated,
            "total": created + updated,
            "sha256": model.sha256,
            "namespace_uri": model.namespace_uri,
            "schema_version": 1,
        }
