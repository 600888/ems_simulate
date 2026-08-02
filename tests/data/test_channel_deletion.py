from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import src.data.dao.channel_dao as channel_dao_module
from src.data.dao.channel_dao import ChannelDao
from src.data.model import (
    Base,
    Channel,
    ChannelProtocolParams,
    ChannelSecurityConfig,
    Device,
    GooseEntry,
    GoosePublisher,
    GooseReceiverConfig,
    GooseSubscriptionConfig,
    PointMapping,
)


def _foreign_key_session_factory(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(channel_dao_module, "local_session", factory)
    return factory


def test_delete_copied_channel_removes_children_before_device(monkeypatch):
    factory = _foreign_key_session_factory(monkeypatch)
    with factory() as session, session.begin():
        device = Device(code="TARGET", name="Target")
        session.add(device)
        session.flush()
        channel = Channel(code="TARGET", name="Target", device_id=device.id)
        session.add(channel)
        session.flush()
        channel_id = channel.id
        device_id = device.id

        session.add_all(
            [
                ChannelProtocolParams(
                    channel_id=channel_id,
                    protocol_type=4,
                    conn_type=2,
                    params_json={},
                ),
                ChannelSecurityConfig(channel_id=channel_id),
                PointMapping(
                    device_name="Target",
                    target_point_code="TOTAL",
                    source_point_codes="[]",
                    formula="0",
                ),
            ]
        )
        publisher = GoosePublisher(
            channel_id=channel_id,
            go_cb_ref="TARGETLD0/LLN0$GO$gcb1",
            data_set_ref="TARGETLD0/LLN0$ds1",
            app_id=1,
        )
        receiver = GooseReceiverConfig(channel_id=channel_id, interface="eth0")
        session.add_all([publisher, receiver])
        session.flush()
        session.add_all(
            [
                GooseEntry(publisher_id=publisher.id, name="TARGETLD0/GGIO1.stVal"),
                GooseSubscriptionConfig(receiver_id=receiver.id, go_cb_ref="REMOTE/LLN0$GO$gcb1"),
            ]
        )

    assert ChannelDao.delete_channel(channel_id) is True

    with factory() as session:
        assert session.get(Channel, channel_id) is None
        assert session.get(Device, device_id) is None
        assert session.query(ChannelProtocolParams).count() == 0
        assert session.query(ChannelSecurityConfig).count() == 0
        assert session.query(GoosePublisher).count() == 0
        assert session.query(GooseEntry).count() == 0
        assert session.query(GooseReceiverConfig).count() == 0
        assert session.query(GooseSubscriptionConfig).count() == 0
        assert session.query(PointMapping).count() == 0


def test_delete_channel_keeps_device_while_another_channel_references_it(monkeypatch):
    factory = _foreign_key_session_factory(monkeypatch)
    with factory() as session, session.begin():
        device = Device(code="SHARED", name="Shared")
        session.add(device)
        session.flush()
        first = Channel(code="FIRST", name="First", device_id=device.id)
        second = Channel(code="SECOND", name="Second", device_id=device.id)
        session.add_all([first, second])
        session.flush()
        first_id = first.id
        second_id = second.id
        device_id = device.id

    assert ChannelDao.delete_channel(first_id) is True

    with factory() as session:
        assert session.get(Channel, first_id) is None
        assert session.get(Channel, second_id) is not None
        assert session.get(Device, device_id) is not None
