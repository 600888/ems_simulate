from unittest.mock import Mock

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


def test_receiver_dao_normalizes_historical_string_mac(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(goose_receiver_dao, "local_session", session_factory)

    receiver_id = goose_receiver_dao.GooseReceiverDao.save(
        1,
        {
            "interface": "eth0",
            "subscriptions": [{"go_cb_ref": "gcb1", "app_id": 1, "dst_mac": "01:0C:CD:01:10:04"}],
        },
    )
    with session_factory.begin() as session:
        subscription = (
            session.query(goose_receiver_dao.GooseSubscriptionConfig).filter_by(receiver_id=receiver_id).one()
        )
        # 模拟旧版本写入的 JSON 字符串，而不是 JSON 数字数组。
        subscription.dst_mac_json = '"01:0C:CD:01:10:04"'

    item = goose_receiver_dao.GooseReceiverDao.list_by_channel(1)[0]["subscriptions"][0]

    assert item["dst_mac"] == [1, 12, 205, 1, 16, 4]


def test_delete_receivers_by_channel_removes_subscriptions_without_fk_cascade(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(goose_receiver_dao, "local_session", session_factory)

    goose_receiver_dao.GooseReceiverDao.save(
        1,
        {"interface": "eth0", "subscriptions": [{"go_cb_ref": "remove", "app_id": 1}]},
    )
    goose_receiver_dao.GooseReceiverDao.save(
        2,
        {"interface": "eth0", "subscriptions": [{"go_cb_ref": "keep", "app_id": 2}]},
    )

    assert goose_receiver_dao.GooseReceiverDao.delete_by_channel(1) == 1
    assert goose_receiver_dao.GooseReceiverDao.list_by_channel(1) == []
    assert len(goose_receiver_dao.GooseReceiverDao.list_by_channel(2)) == 1
    with session_factory() as session:
        subscriptions = session.query(goose_receiver_dao.GooseSubscriptionConfig).all()
        assert [item.go_cb_ref for item in subscriptions] == ["keep"]


def test_delete_receivers_by_channel_clears_runtime_indexes():
    manager = manager_module.GooseResourceManager(PersistenceAdapter(_Backend()))
    remove = Mock()
    keep = Mock()
    keep.get_status.return_value = {}
    manager._receivers = {"remove": remove, "keep": keep}
    manager._receiver_channel_map = {"remove": 1, "keep": 2}
    manager._receiver_meta = {
        "remove": {"interface_key": "1:eth0:default"},
        "keep": {"interface_key": "2:eth0:default"},
    }
    manager._interface_to_rid = {
        "1:eth0:default": "remove",
        "2:eth0:default": "keep",
    }

    assert manager.delete_receivers_by_channel(1) == 1
    remove.stop.assert_called_once_with()
    keep.stop.assert_not_called()
    assert manager.list_receivers(1) == []
    assert [item["id"] for item in manager.list_receivers(2)] == ["keep"]
    assert manager._interface_to_rid == {"2:eth0:default": "keep"}


def test_list_receivers_isolates_one_broken_receiver_status():
    manager = manager_module.GooseResourceManager(PersistenceAdapter(_Backend()))
    broken = Mock()
    healthy = Mock()
    broken.get_status.side_effect = ValueError("invalid historical subscription")
    healthy.get_status.return_value = {"subscriptions": []}
    manager._receivers = {"broken": broken, "healthy": healthy}
    manager._receiver_channel_map = {"broken": 1, "healthy": 1}

    results = manager.list_receivers(1)

    assert results[0] == {
        "id": "broken",
        "error": "invalid historical subscription",
        "subscriptions": [],
    }
    assert results[1]["id"] == "healthy"
