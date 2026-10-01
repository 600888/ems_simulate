"""Persistence and validation for the first OPC UA variable types."""

from typing import Any

from sqlalchemy import select

from src.data.controller.db import local_session
from src.data.model.opcua_node import OpcUaNode
from src.data.model.opcua_point import OpcUaPoint
from src.proto.opcua.core.model import validate_variable


class OpcUaNodeService:
    @staticmethod
    def has_nodes(channel_id: int) -> bool:
        with local_session() as session:
            return session.scalar(select(OpcUaNode.id).where(OpcUaNode.channel_id == channel_id).limit(1)) is not None

    @staticmethod
    def list_nodes(channel_id: int) -> list[dict[str, Any]]:
        with local_session() as session:
            point_codes = dict(
                session.execute(
                    select(OpcUaPoint.node_id, OpcUaPoint.point_code).where(
                        OpcUaPoint.channel_id == channel_id,
                    )
                ).all()
            )
            records = session.scalars(
                select(OpcUaNode).where(OpcUaNode.channel_id == channel_id).order_by(OpcUaNode.node_id)
            ).all()
            return [
                {
                    "namespace_uri": row.namespace_uri,
                    "node_id": row.node_id,
                    "browse_name": row.browse_name,
                    "data_type": row.data_type,
                    "initial_value": row.initial_value,
                    "writable": row.writable,
                    "point_code": point_codes.get(row.node_id),
                }
                for row in records
            ]

    @staticmethod
    def upsert_variable(channel_id: int, namespace_uri: str, data: dict[str, Any]) -> dict[str, Any]:
        normalized = validate_variable(data)
        if not namespace_uri or len(namespace_uri) > 255:
            raise ValueError("命名空间 URI 必须在 1 到 255 个字符之间")
        with local_session() as session, session.begin():
            if (
                session.scalar(
                    select(OpcUaPoint.id)
                    .where(
                        OpcUaPoint.channel_id == channel_id,
                        OpcUaPoint.node_id == normalized["node_id"],
                    )
                    .limit(1)
                )
                is not None
            ):
                raise ValueError("节点属于 Excel 点表，请通过点表覆盖更新")
            record = session.scalar(
                select(OpcUaNode).where(
                    OpcUaNode.channel_id == channel_id,
                    OpcUaNode.node_id == normalized["node_id"],
                )
            )
            if record is None:
                record = OpcUaNode(channel_id=channel_id, namespace_uri=namespace_uri, **normalized)
                session.add(record)
            else:
                if record.namespace_uri != namespace_uri:
                    raise ValueError("NodeId 已属于其他命名空间 URI")
                for key, value in normalized.items():
                    setattr(record, key, value)
        return {"namespace_uri": namespace_uri, **normalized}

    @staticmethod
    def delete_variable(channel_id: int, node_id: str) -> bool:
        with local_session() as session, session.begin():
            if (
                session.scalar(
                    select(OpcUaPoint.id)
                    .where(
                        OpcUaPoint.channel_id == channel_id,
                        OpcUaPoint.node_id == node_id,
                    )
                    .limit(1)
                )
                is not None
            ):
                raise ValueError("节点属于 Excel 点表，请在测点管理中删除")
            record = session.scalar(
                select(OpcUaNode).where(
                    OpcUaNode.channel_id == channel_id,
                    OpcUaNode.node_id == node_id,
                )
            )
            if record is None:
                return False
            session.delete(record)
        return True
