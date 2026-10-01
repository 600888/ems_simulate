"""Persistence for desired configuration shared by API and lifecycle builders."""

from copy import deepcopy

from sqlalchemy import select

from src.data.controller.db import local_session
from src.data.model.channel import Channel
from src.data.model.opcua_feature import OpcUaFeature


class OpcUaFeatureService:
    @staticmethod
    def load(channel_id: int) -> dict:
        with local_session() as session:
            return {
                row.name: deepcopy(row.config)
                for row in session.scalars(select(OpcUaFeature).where(OpcUaFeature.channel_id == channel_id))
            }

    @staticmethod
    def save(channel_id: int, name: str, config: dict) -> dict:
        with local_session() as session, session.begin():
            channel = session.get(Channel, channel_id)
            if channel is None or channel.protocol_type != 7:
                raise ValueError("OPC UA 通道不存在")
            row = session.get(OpcUaFeature, (channel_id, name))
            if row is None:
                session.add(OpcUaFeature(channel_id=channel_id, name=name, config=deepcopy(config)))
            else:
                row.config = deepcopy(config)
        return config
