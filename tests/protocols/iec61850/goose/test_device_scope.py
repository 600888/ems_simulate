from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.data.dao import goose_publisher_dao, goose_receiver_dao
import src.data.model  # noqa: F401
from src.data.model.base import Base
from src.proto.iec61850.plugins.goose import manager as manager_module
from src.proto.iec61850.plugins.goose.capture import CapturedPacket
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


def test_remove_last_subscription_deletes_receiver_and_runtime_index(monkeypatch):
    manager = manager_module.GooseResourceManager(PersistenceAdapter(_Backend()))
    receiver = Mock()
    receiver.is_running = False
    receiver.remove_subscription.return_value = True
    receiver.get_subscriptions.return_value = []
    manager._receivers = {"3": receiver}
    manager._receiver_channel_map = {"3": 1}
    manager._receiver_meta = {
        "3": {"db_id": 3, "interface_key": "1:WLAN:default"},
    }
    manager._interface_to_rid = {"1:WLAN:default": "3"}
    delete = Mock(return_value=True)
    monkeypatch.setattr(goose_receiver_dao.GooseReceiverDao, "delete", delete)

    assert manager.remove_subscription("3", "LD0/LLN0$GO$gcb1") is True

    receiver.stop.assert_called_once_with()
    delete.assert_called_once_with(3, 1)
    assert manager._receivers == {}
    assert manager._receiver_channel_map == {}
    assert manager._receiver_meta == {}
    assert manager._interface_to_rid == {}


@pytest.fixture
def receiver_manager(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(goose_receiver_dao, "local_session", sessionmaker(engine, expire_on_commit=False))
    return manager_module.GooseResourceManager()


@pytest.mark.parametrize("running", [False, True])
def test_update_receiver_keeps_subscriptions_and_runtime_id(monkeypatch, receiver_manager, running):
    manager = receiver_manager
    created = manager.create_receiver(
        channel_id=1,
        interface="eth0",
        subscriptions=[{"go_cb_ref": "gcb1", "enabled": True}, {"go_cb_ref": "gcb2"}],
    )
    rid = created["id"]
    receiver = manager._receivers[rid]
    receiver._on_captured_packet(
        CapturedPacket(timestamp=1000, src_mac="", dst_mac="", raw_bytes=b"", length=0, go_cb_ref="gcb1")
    )
    subscriptions = receiver.get_subscriptions()
    history = receiver.get_history("gcb1")
    receiver._is_running = running
    start = Mock(side_effect=lambda: setattr(receiver, "_is_running", True) or True)
    stop = Mock(side_effect=lambda: setattr(receiver, "_is_running", False))
    monkeypatch.setattr(receiver, "start", start)
    monkeypatch.setattr(receiver, "stop", stop)

    updated = manager.update_receiver(rid, "eth1")

    assert manager._receivers[rid] is receiver
    assert updated["id"] == rid
    assert updated["db_id"] == created["db_id"]
    assert updated["interface"] == "eth1"
    assert updated["is_running"] is running
    assert updated["subscriptions"] == subscriptions
    assert receiver.get_history("gcb1") == history
    assert manager._interface_to_rid == {"1:eth1:default": rid}
    assert start.call_count == stop.call_count == int(running)
    saved = goose_receiver_dao.GooseReceiverDao.list_by_channel(1)
    assert [(item["db_id"], item["interface"]) for item in saved] == [(created["db_id"], "eth1")]
    assert [sub["go_cb_ref"] for sub in saved[0]["subscriptions"]] == ["gcb1", "gcb2"]


def test_update_receiver_rejects_interface_conflict_without_removing_subscriptions(receiver_manager):
    manager = receiver_manager
    source = manager.create_receiver(channel_id=1, interface="eth0", subscriptions=[{"go_cb_ref": "gcb1"}])
    target = manager.create_receiver(channel_id=1, interface="eth1", subscriptions=[{"go_cb_ref": "gcb2"}])

    with pytest.raises(ValueError, match="已存在同名 GOOSE Receiver"):
        manager.update_receiver(source["id"], "eth1")

    assert manager.list_receivers(1) == [source, target]
    assert manager._interface_to_rid == {"1:eth0:default": source["id"], "1:eth1:default": target["id"]}


@pytest.mark.parametrize("failure", ["start", "save"])
def test_update_receiver_rolls_back_interface_when_reconfiguration_fails(monkeypatch, receiver_manager, failure):
    manager = receiver_manager
    created = manager.create_receiver(
        channel_id=1, interface="eth0", subscriptions=[{"go_cb_ref": "gcb1", "enabled": True}]
    )
    rid = created["id"]
    receiver = manager._receivers[rid]
    receiver._is_running = True
    start_interfaces = []

    def start():
        start_interfaces.append(receiver.interface)
        receiver._is_running = failure != "start" or receiver.interface == "eth0"
        return receiver._is_running

    monkeypatch.setattr(receiver, "start", start)
    monkeypatch.setattr(receiver, "stop", lambda: setattr(receiver, "_is_running", False))
    dao = goose_receiver_dao.GooseReceiverDao
    if failure == "save":
        # A persisted Receiver may exist before its runtime resource is loaded.
        dao.save(1, {"interface": "eth1", "subscriptions": [{"go_cb_ref": "gcb2"}]})
    saved = dao.list_by_channel(1)
    error = RuntimeError if failure == "start" else IntegrityError
    with pytest.raises(error):
        manager.update_receiver(rid, "eth1")

    assert start_interfaces == ["eth1", "eth0"]
    assert manager.get_receiver_status(rid) == {**created, "is_running": True}
    assert manager._interface_to_rid == {"1:eth0:default": rid}
    assert dao.list_by_channel(1) == saved


def test_import_discovered_adds_disabled_subscription_and_restarts_running_receiver(monkeypatch):
    manager = manager_module.GooseResourceManager(PersistenceAdapter(_Backend()))
    receiver = Mock()
    receiver.is_running = True
    receiver.start.return_value = True
    receiver.get_subscription.return_value = None
    receiver.get_status.return_value = {"subscriptions": []}
    manager._receivers = {"3": receiver}
    manager._receiver_channel_map = {"3": 1}
    manager._receiver_meta = {"3": {"db_id": 3}}
    manager._interface_to_rid = {"1:WLAN:default": "3"}
    persist = Mock()
    monkeypatch.setattr(manager, "_persist_receiver", persist)

    result = manager.import_discovered(
        [{"go_cb_ref": "LD0/LLN0$GO$gcb1", "app_id": 1}],
        interface="WLAN",
        channel_id=1,
    )

    receiver.stop.assert_called_once_with()
    receiver.add_subscription.assert_called_once_with(
        go_cb_ref="LD0/LLN0$GO$gcb1",
        app_id=1,
        dst_mac=None,
        description="auto-discovered",
        data_set_ref="",
        conf_rev=0,
        enabled=False,
        ied_name="",
        ld_inst="",
        ln_name="LLN0",
        dataset_entries=[],
        go_id="",
    )
    persist.assert_called_once_with("3")
    receiver.start.assert_called_once_with()
    assert result["id"] == "3"


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
