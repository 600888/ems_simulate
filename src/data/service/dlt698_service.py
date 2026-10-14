"""Transactional persistence for DL/T 698 configuration and point definitions."""

from copy import deepcopy

from sqlalchemy import select

from src.data.controller.db import local_session
from src.data.model.channel import Channel
from src.data.model.channel_configuration import ChannelProtocolParams
from src.data.model.dlt698 import Dlt698Point
from src.proto.dlt698.catalog import standard_definition
from src.proto.dlt698.schema import Dlt698Config, Point


class Dlt698Service:
    @staticmethod
    def config(channel_id: int) -> Dlt698Config:
        with local_session() as session:
            channel = session.get(Channel, channel_id)
            if channel is None or channel.protocol_type != 8:
                raise ValueError("DL/T 698 通道不存在")
            record = session.get(ChannelProtocolParams, channel_id)
            if record and record.protocol_type == 8:
                return Dlt698Config.model_validate(record.params_json)
            return Dlt698Config(role="client" if channel.conn_type in (0, 1) else "server")

    @staticmethod
    def save_config(channel_id: int, config: Dlt698Config):
        with local_session() as session, session.begin():
            channel = session.get(Channel, channel_id)
            if not channel or channel.protocol_type != 8:
                raise ValueError("DL/T 698 通道不存在")
            record = session.get(ChannelProtocolParams, channel_id)
            if record is None:
                record = ChannelProtocolParams(channel_id=channel_id)
                session.add(record)
            record.protocol_type, record.conn_type = 8, channel.conn_type
            record.schema_version, record.params_json = 1, config.model_dump()

    @staticmethod
    def points(channel_id: int) -> list[dict]:
        with local_session() as session:
            return [
                deepcopy(row.definition)
                for row in session.scalars(
                    select(Dlt698Point).where(Dlt698Point.channel_id == channel_id).order_by(Dlt698Point.id)
                )
            ]

    @classmethod
    def save_points(cls, channel_id: int, points: list[Point], original_code: str | None = None):
        config = cls.config(channel_id)
        normalized = [standard_definition(point, config) for point in points]
        if config.role == "server" and any(point.writable for point in normalized):
            raise ValueError("dlt698 1.0 托管服务端只支持只读属性；客户端仍可向对端发送 SET")
        codes = [point.code for point in normalized]
        if len(codes) != len(set(codes)):
            raise ValueError("导入批次存在重复测点编码")
        with local_session() as session, session.begin():
            current = {
                row.code: row
                for row in session.scalars(select(Dlt698Point).where(Dlt698Point.channel_id == channel_id))
            }
            if original_code is not None and original_code not in current:
                raise ValueError("测点不存在")
            prospective = {code: row.definition for code, row in current.items() if code != original_code}
            prospective.update({point.code: point.model_dump(exclude_none=True) for point in normalized})
            if config.role == "server":
                from src.proto.dlt698.runtime import Dlt698Runtime

                # Ask the library to validate a prospective publication before saving any rows.
                Dlt698Runtime(config, {}, prospective.values())._make_device()
            for point in normalized:
                if point.code in current and point.code != original_code:
                    raise ValueError(f"测点编码已存在: {point.code}")
                row = current.get(original_code) if original_code else None
                if row is None:
                    row = Dlt698Point(channel_id=channel_id, code=point.code)
                    session.add(row)
                row.code, row.definition = point.code, point.model_dump(exclude_none=True)
        return [point.model_dump(exclude_none=True) for point in normalized]

    @staticmethod
    def delete_point(channel_id: int, code: str):
        with local_session() as session, session.begin():
            row = session.scalar(
                select(Dlt698Point).where(Dlt698Point.channel_id == channel_id, Dlt698Point.code == code)
            )
            if row is None:
                raise ValueError("测点不存在")
            session.delete(row)

    @staticmethod
    def clone(source: int, target: int):
        with local_session() as session, session.begin():
            for point in session.scalars(select(Dlt698Point).where(Dlt698Point.channel_id == source)):
                session.add(Dlt698Point(channel_id=target, code=point.code, definition=deepcopy(point.definition)))
