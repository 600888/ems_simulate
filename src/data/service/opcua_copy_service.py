"""Copy one channel's UA configuration and model without sharing mutable records."""

from copy import deepcopy
from urllib.parse import urlparse

from sqlalchemy import select

from src.data.controller.db import local_session
from src.data.model.channel import Channel
from src.data.model.opcua_config import OpcUaConfig
from src.data.model.opcua_node import OpcUaNode
from src.data.model.opcua_point import OpcUaPoint
from src.proto.opcua.core.transport import loopback_endpoint, make_endpoint_url


class OpcUaCopyService:
    @staticmethod
    def clone_for_channel(source_id: int, target_id: int) -> dict[str, int]:
        with local_session() as session, session.begin():
            source = session.get(Channel, source_id)
            target = session.get(Channel, target_id)
            if source is None or target is None or source_id == target_id:
                raise ValueError("源通道或目标通道无效")
            if source.protocol_type != 7 or target.protocol_type != 7 or source.conn_type != target.conn_type:
                raise ValueError("OPC UA 复制必须使用相同的协议和客户端/服务端角色")
            if session.get(OpcUaConfig, target_id) is not None or any(
                session.scalar(select(model.id).where(model.channel_id == target_id).limit(1)) is not None
                for model in (OpcUaNode, OpcUaPoint)
            ):
                raise ValueError("目标通道已有 OPC UA 配置或模型")
            config = session.get(OpcUaConfig, source_id)
            endpoint_path = config.endpoint_path if config else "/ems/"
            namespace_uri = (config.namespace_uri if config else None) or f"urn:ems-simulate:channel:{source_id}"
            source_endpoint = config.endpoint_url if config else None
            if source.conn_type == 1 and source_endpoint:
                endpoint_path = urlparse(source_endpoint).path or "/"
            endpoint = loopback_endpoint(make_endpoint_url(target.ip, target.port, endpoint_path))
            session.add(
                OpcUaConfig(
                    channel_id=target_id,
                    schema_version=config.schema_version if config else 1,
                    endpoint_url=endpoint if target.conn_type == 1 else None,
                    endpoint_path=config.endpoint_path if config else "/ems/",
                    namespace_uri=namespace_uri,
                )
            )
            counts = {}
            for model, name in ((OpcUaNode, "node_count"), (OpcUaPoint, "point_count")):
                records = session.scalars(select(model).where(model.channel_id == source_id)).all()
                fields = [column.name for column in model.__table__.columns if column.name not in {"id", "channel_id"}]
                for record in records:
                    payload = {field: deepcopy(getattr(record, field)) for field in fields}
                    session.add(model(channel_id=target_id, **payload))
                counts[name] = len(records)
        return counts
