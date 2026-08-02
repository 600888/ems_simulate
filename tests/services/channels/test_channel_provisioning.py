import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import src.data.model  # noqa: F401
from src.data.model.base import Base
from src.data.model.channel import Channel
from src.data.model.device import Device
from src.data.service import channel_service as channel_service_module
from src.data.service.channel_service import ChannelService


def test_channel_provisioning_rolls_back_the_whole_aggregate(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(channel_service_module, "local_session", factory)

    values = {
        "code": "DEV1",
        "name": "Device 1",
        "group_id": None,
        "protocol_type": 1,
        "conn_type": 2,
        "protocol_params": None,
        "ip": "127.0.0.1",
        "port": 502,
    }
    ChannelService.provision_channel(**values)

    with pytest.raises(IntegrityError):
        ChannelService.provision_channel(**values)

    with factory() as session:
        assert session.scalar(select(func.count(Device.id))) == 1
        assert session.scalar(select(func.count(Channel.id))) == 1


def test_channel_provisioning_persists_dlt645_point_mode(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(channel_service_module, "local_session", factory)

    _device_id, channel_id = ChannelService.provision_channel(
        code="DLT1",
        name="DLT645",
        group_id=None,
        protocol_type=3,
        conn_type=1,
        protocol_params=None,
        ip="127.0.0.1",
        port=8899,
        dlt645_point_mode="standard",
    )

    with factory() as session:
        channel = session.get(Channel, channel_id)
        assert channel is not None
        assert channel.dlt645_point_mode == "standard"
