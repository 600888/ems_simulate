from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data.dao import goose_publisher_dao, goose_receiver_dao
import src.data.model  # noqa: F401
from src.data.model.base import Base
from src.proto.iec61850.plugins.goose import manager as manager_module
from src.proto.iec61850.plugins.goose.persistence import PersistenceAdapter


class _Backend:
    def __init__(self):
        self.saved = []

    def save_publisher(self, channel_id, status):
        self.saved.append((channel_id, status))
        return len(self.saved)

    def delete_publisher_by_go_cb_ref(self, _go_cb_ref):
        return True


class _Publisher:
    def __init__(self, config):
        self.config = config
        self.is_running = False
        self.go_cb_ref = config.go_cb_ref
        self._entries = []

    def add_entry(self, entry):
        self._entries.append(entry)

    def get_entries(self):
        return [
            {"index": index, "name": item.name, "value": item.value, "iec_type": item.iec_type.value}
            for index, item in enumerate(self._entries)
        ]

    def get_status(self):
        return {
            "go_cb_ref": self.config.go_cb_ref,
            "go_id": self.config.go_id,
            "data_set_ref": self.config.data_set_ref,
            "app_id": self.config.app_id,
            "conf_rev": self.config.conf_rev,
            "time_allowed_to_live": self.config.time_allowed_to_live,
            "interface": self.config.interface,
            "simulation": self.config.simulation,
            "is_running": self.is_running,
            "dst_mac": self.config.dst_mac,
            "vlan_id": self.config.vlan_id,
            "vlan_prio": self.config.vlan_prio,
        }

    def stop(self):
        self.is_running = False


def test_publishers_are_isolated_by_channel(monkeypatch):
    monkeypatch.setattr(manager_module, "HAS_IEC61850", True)
    monkeypatch.setattr(manager_module, "GoosePublisher", _Publisher)
    backend = _Backend()
    manager = manager_module.GooseResourceManager(PersistenceAdapter(backend))

    first = manager.create_publisher(channel_id=1, interface="eth0", go_cb_ref="LD0/LLN0$GO$gcb1")
    second = manager.create_publisher(channel_id=2, interface="eth0", go_cb_ref="LD0/LLN0$GO$gcb1")

    assert first and second and first["id"] != second["id"]
    assert [item["channel_id"] for item in manager.list_publishers(1)] == [1]
    assert [item["channel_id"] for item in manager.list_publishers(2)] == [2]
    assert len(backend.saved) == 2


def test_delete_publishers_by_channel_only_removes_target_channel(monkeypatch):
    monkeypatch.setattr(manager_module, "HAS_IEC61850", True)
    monkeypatch.setattr(manager_module, "GoosePublisher", _Publisher)
    manager = manager_module.GooseResourceManager(PersistenceAdapter(_Backend()))
    manager.create_publisher(channel_id=1, go_cb_ref="old-a")
    manager.create_publisher(channel_id=1, go_cb_ref="old-b")
    manager.create_publisher(channel_id=2, go_cb_ref="keep")

    assert manager.delete_publishers_by_channel(1) == 2
    assert manager.list_publishers(1) == []
    assert [item["go_cb_ref"] for item in manager.list_publishers(2)] == ["keep"]


def test_delete_by_channel_removes_publishers_datasets_and_entries(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(goose_publisher_dao, "local_session", session_factory)

    goose_publisher_dao.GoosePublisherDao.save_publisher(
        1,
        {"go_cb_ref": "old", "entries": [{"name": "old-entry", "value": True}]},
    )
    goose_publisher_dao.GoosePublisherDao.save_pure_dataset(
        1,
        "LD0",
        "dsOld",
        "LD0/LLN0$dsOld",
        [{"name": "old-dataset-entry", "value": 1}],
    )
    goose_publisher_dao.GoosePublisherDao.save_publisher(2, {"go_cb_ref": "keep"})
    goose_publisher_dao.GoosePublisherDao.save_pure_dataset(
        2,
        "LD0",
        "dsOld",
        "LD0/LLN0$dsOld",
        [{"name": "keep-dataset-entry", "value": 2}],
    )

    assert goose_publisher_dao.GoosePublisherDao.delete_by_channel(1) == 2
    assert goose_publisher_dao.GoosePublisherDao.get_by_channel(1) == []
    assert goose_publisher_dao.GoosePublisherDao.get_pure_datasets_by_channel(1) == []
    assert [item["go_cb_ref"] for item in goose_publisher_dao.GoosePublisherDao.get_by_channel(2)] == ["keep"]
    assert len(goose_publisher_dao.GoosePublisherDao.get_pure_datasets_by_channel(2)) == 1
    with session_factory() as session:
        assert session.query(goose_publisher_dao.GooseEntry).count() == 1


def test_stopped_publisher_supports_full_config_update(monkeypatch):
    monkeypatch.setattr(manager_module, "HAS_IEC61850", True)
    monkeypatch.setattr(manager_module, "GoosePublisher", _Publisher)
    manager = manager_module.GooseResourceManager(PersistenceAdapter(_Backend()))
    created = manager.create_publisher(channel_id=7, interface="eth0", go_cb_ref="old", app_id=1)

    updated = manager.update_publisher(
        created["id"],
        interface="eth1",
        go_cb_ref="new",
        data_set_ref="LD0/LLN0$ds1",
        app_id=0x1001,
        vlan_id=100,
        vlan_prio=6,
        simulation=False,
    )

    assert updated["interface"] == "eth1"
    assert updated["go_cb_ref"] == "new"
    assert updated["app_id"] == 0x1001
    assert updated["vlan_id"] == 100


def test_receiver_subscriptions_are_persisted_and_replaceable(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(goose_receiver_dao, "local_session", sessionmaker(engine, expire_on_commit=False))

    receiver_id = goose_receiver_dao.GooseReceiverDao.save(
        1,
        {
            "interface": "eth0",
            "name": "default",
            "subscriptions": [{"go_cb_ref": "gcb1", "app_id": 1}],
        },
    )
    goose_receiver_dao.GooseReceiverDao.save(
        1,
        {
            "db_id": receiver_id,
            "interface": "eth0",
            "name": "default",
            "subscriptions": [{"go_cb_ref": "gcb2", "app_id": 2}],
        },
    )

    items = goose_receiver_dao.GooseReceiverDao.list_by_channel(1)
    assert len(items) == 1
    assert [item["go_cb_ref"] for item in items[0]["subscriptions"]] == ["gcb2"]
