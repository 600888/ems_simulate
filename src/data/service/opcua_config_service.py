"""OPC UA endpoint configuration and channel address consistency."""

from urllib.parse import urlparse

from sqlalchemy import select

from src.data.controller.db import local_session
from src.data.model.channel import Channel
from src.data.model.opcua_config import OpcUaConfig
from src.data.model.opcua_node import OpcUaNode
from src.proto.opcua.core.transport import loopback_endpoint, make_endpoint_url


class OpcUaConfigService:
    @staticmethod
    def get(channel_id: int) -> dict:
        with local_session() as session:
            channel = session.get(Channel, channel_id)
            if channel is None or channel.protocol_type != 7:
                raise ValueError("OPC UA 通道不存在")
            record = session.get(OpcUaConfig, channel_id)
            endpoint_path = record.endpoint_path if record else "/ems/"
            namespace_uri = (record.namespace_uri if record else None) or f"urn:ems-simulate:channel:{channel_id}"
            endpoint_url = (record.endpoint_url if record else None) or make_endpoint_url(
                channel.ip, channel.port, endpoint_path
            )
            return {
                "channel_id": channel_id,
                "role": "client" if channel.conn_type == 1 else "server",
                "endpoint_url": endpoint_url,
                "endpoint_path": endpoint_path,
                "namespace_uri": namespace_uri,
                "bind_host": channel.ip,
                "bind_port": channel.port,
            }

    @staticmethod
    def save_client_endpoint(channel_id: int, endpoint_url: str) -> dict:
        loopback_endpoint(endpoint_url)
        parsed = urlparse(endpoint_url)
        with local_session() as session, session.begin():
            channel = session.get(Channel, channel_id)
            if channel is None or channel.protocol_type != 7 or channel.conn_type != 1:
                raise ValueError("OPC UA 客户端通道不存在")
            record = session.get(OpcUaConfig, channel_id)
            if record is None:
                record = OpcUaConfig(channel_id=channel_id)
                session.add(record)
            record.endpoint_url = endpoint_url
            channel.ip = parsed.hostname
            channel.port = parsed.port
        return OpcUaConfigService.get(channel_id)

    @staticmethod
    def save_server_model(channel_id: int, endpoint_path: str, namespace_uri: str) -> dict:
        if not endpoint_path.startswith("/") or "?" in endpoint_path or "#" in endpoint_path:
            raise ValueError("Endpoint 路径必须以 / 开头，且不含查询参数或片段")
        if not namespace_uri or len(namespace_uri) > 255:
            raise ValueError("命名空间 URI 必须在 1 到 255 个字符之间")
        with local_session() as session, session.begin():
            channel = session.get(Channel, channel_id)
            if channel is None or channel.protocol_type != 7 or channel.conn_type != 2:
                raise ValueError("OPC UA 服务端通道不存在")
            loopback_endpoint(make_endpoint_url(channel.ip, channel.port, endpoint_path))
            record = session.get(OpcUaConfig, channel_id)
            old_uri = (record.namespace_uri if record else None) or f"urn:ems-simulate:channel:{channel_id}"
            if (
                old_uri != namespace_uri
                and session.scalar(select(OpcUaNode.id).where(OpcUaNode.channel_id == channel_id).limit(1)) is not None
            ):
                raise ValueError("已有节点定义时不能更改命名空间 URI")
            if record is None:
                record = OpcUaConfig(channel_id=channel_id)
                session.add(record)
            record.endpoint_path = endpoint_path
            record.namespace_uri = namespace_uri
        return OpcUaConfigService.get(channel_id)
