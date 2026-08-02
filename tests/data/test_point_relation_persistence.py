from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import src.data.dao.point_dao as point_dao_module
from src.data.dao.point_dao import PointDao
from src.data.model import Base, Channel, Device


def test_create_points_persists_copyable_relation_fields(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(point_dao_module, "local_session", factory)

    with factory() as session, session.begin():
        device = Device(code="TARGET", name="Target")
        session.add(device)
        session.flush()
        channel = Channel(code="TARGET", name="Target", device_id=device.id)
        session.add(channel)
        session.flush()
        channel_id = channel.id

    yc = PointDao.create_yc(channel_id, {"code": "YC", "name": "YC", "reg_addr": "1"})
    yx = PointDao.create_yx(
        channel_id,
        {"code": "YX", "name": "YX", "reg_addr": "2", "reverse": True, "enable": False},
    )
    yk = PointDao.create_yk(
        channel_id,
        {
            "code": "YK",
            "name": "YK",
            "reg_addr": "3",
            "command_type": 1,
            "related_yx_id": yx["id"],
        },
    )
    yt = PointDao.create_yt(
        channel_id,
        {"code": "YT", "name": "YT", "reg_addr": "4", "related_yc_id": yc["id"]},
    )

    assert yx["reverse"] is True
    assert yx["enable"] is False
    assert yk["command_type"] == 1
    assert yk["related_yx_id"] == yx["id"]
    assert yt["related_yc_id"] == yc["id"]
