"""IEC 61850 device-copy persistence tests."""

import json
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data.model.base import Base
from src.data.model.goose_publisher import GooseEntry, GoosePublisher
from src.data.model.goose_receiver import GooseReceiverConfig, GooseSubscriptionConfig
import src.data.service.iec61850_copy_service as copy_service_module
from src.data.service.iec61850_copy_service import Iec61850CopyService


def _session_factory(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(copy_service_module, "local_session", factory)
    return factory


def test_clone_persistent_resources_deep_copies_goose_and_datasets(monkeypatch):
    factory = _session_factory(monkeypatch)
    with factory() as session, session.begin():
        publisher = GoosePublisher(
            channel_id=10,
            interface="Ethernet 1",
            go_cb_ref="IEDLD0/LLN0$GO$gcb1",
            go_id="trip",
            data_set_ref="IEDLD0/LLN0$dsTrip",
            app_id=0x1001,
            conf_rev=7,
            time_allowed_to_live=2000,
            dst_mac_json=json.dumps([1, 12, 205, 1, 0, 1]),
            vlan_id=12,
            vlan_prio=5,
            simulation=False,
            name="Trip publisher",
            description="source publisher",
            auto_start=True,
        )
        dataset = GoosePublisher(
            channel_id=10,
            interface="",
            go_cb_ref="__pure__IEDLD0/LLN0$dsMeasurements",
            go_id="LD0",
            data_set_ref="IEDLD0/LLN0$dsMeasurements",
            app_id=0,
            simulation=False,
        )
        session.add_all([publisher, dataset])
        session.flush()
        session.add_all(
            [
                GooseEntry(
                    publisher_id=publisher.id,
                    name="IEDLD0/GGIO1.SPCSO1.stVal",
                    value="true",
                    iec_type="boolean",
                    sort_order=0,
                ),
                GooseEntry(
                    publisher_id=dataset.id,
                    name="IEDLD0/MMXU1.TotW.mag.f",
                    value="12.5",
                    iec_type="float",
                    sort_order=0,
                ),
            ]
        )
        receiver = GooseReceiverConfig(
            channel_id=10,
            name="remote-ied",
            description="receiver",
            interface="Ethernet 2",
            auto_start=True,
        )
        session.add(receiver)
        session.flush()
        session.add(
            GooseSubscriptionConfig(
                receiver_id=receiver.id,
                go_cb_ref="REMOTE/LLN0$GO$gcb1",
                app_id=0x1002,
                dst_mac_json=json.dumps([1, 12, 205, 1, 0, 2]),
                description="remote trip",
                data_set_ref="REMOTE/LLN0$dsTrip",
                conf_rev=3,
                enabled=True,
                ied_name="REMOTE",
                ld_inst="LD0",
                ln_name="LLN0",
                dataset_entries_json=json.dumps([{"name": "GGIO1.SPCSO1.stVal"}]),
                go_id="remote-trip",
            )
        )

    result = Iec61850CopyService._clone_persistent_resources(10, 20)

    assert result == {
        "publisher_count": 1,
        "dataset_count": 1,
        "receiver_count": 1,
        "subscription_count": 1,
    }
    with factory() as session:
        copied_publishers = (
            session.query(GoosePublisher).where(GoosePublisher.channel_id == 20).order_by(GoosePublisher.id).all()
        )
        assert len(copied_publishers) == 2
        copied_publisher = next(item for item in copied_publishers if not item.go_cb_ref.startswith("__pure__"))
        assert copied_publisher.id != publisher.id
        assert copied_publisher.go_cb_ref == publisher.go_cb_ref
        assert copied_publisher.auto_start is True
        assert copied_publisher.entries[0].name == "IEDLD0/GGIO1.SPCSO1.stVal"

        copied_receiver = session.query(GooseReceiverConfig).where(GooseReceiverConfig.channel_id == 20).one()
        assert copied_receiver.id != receiver.id
        assert copied_receiver.auto_start is True
        assert copied_receiver.subscriptions[0].go_cb_ref == "REMOTE/LLN0$GO$gcb1"
        assert copied_receiver.subscriptions[0].dataset_entries_json == json.dumps([{"name": "GGIO1.SPCSO1.stVal"}])


def test_clone_for_channel_creates_independent_verified_model_file(monkeypatch, tmp_path):
    _session_factory(monkeypatch)
    source_model = tmp_path / "source" / "IED.icd"
    source_model.parent.mkdir()
    source_model.write_text("<SCL><IED name='IED'/></SCL>", encoding="utf-8")

    from src.proto.iec61850.plugins.scl.service import file_manager as file_manager_module

    monkeypatch.setattr(file_manager_module, "get_storage_path", lambda _name: str(tmp_path / "storage"))
    updates = []
    monkeypatch.setattr(
        copy_service_module.ChannelService,
        "set_icd_path",
        lambda channel_id, path, file_hash: updates.append((channel_id, path, file_hash)) or True,
    )

    result = Iec61850CopyService.clone_for_channel(
        {
            "id": 10,
            "protocol_type": 4,
            "icd_path": str(source_model),
            "icd_file_hash": file_manager_module.SclFileManager.compute_hash_from_file(str(source_model)),
        },
        target_channel_id=20,
        target_device_id=30,
        target_device_name="IED_COPY1",
    )

    copied_model = tmp_path / "storage" / "device" / "IED_COPY1" / "IED_ch20.icd"
    assert result.model_copied is True
    assert result.model_path == str(copied_model)
    assert copied_model.read_bytes() == source_model.read_bytes()
    assert copied_model != source_model
    assert Path(f"{copied_model}.sha256").is_file()
    metadata = json.loads(Path(f"{copied_model}.meta").read_text(encoding="utf-8"))
    assert metadata["device_ids"] == [30]
    assert metadata["channel_ids"] == [20]
    assert updates == [(20, str(copied_model), result.model_hash)]


def test_hydrate_runtime_resources_keeps_copied_goose_stopped(monkeypatch):
    from src.data.dao import goose_publisher_dao, goose_receiver_dao

    publisher = {
        "interface": "Ethernet 1",
        "go_cb_ref": "IEDLD0/LLN0$GO$gcb1",
        "go_id": "trip",
        "data_set_ref": "IEDLD0/LLN0$dsTrip",
        "app_id": 0x1001,
        "entries": [{"name": "GGIO1.SPCSO1.stVal", "value": False, "iec_type": "boolean"}],
        "name": "Trip publisher",
        "auto_start": True,
    }
    receiver = {
        "db_id": 8,
        "interface": "Ethernet 2",
        "name": "remote",
        "description": "Remote IED",
        "auto_start": True,
        "subscriptions": [{"go_cb_ref": "REMOTE/LLN0$GO$gcb1", "enabled": True}],
    }
    saved_publishers = []
    monkeypatch.setattr(goose_publisher_dao.GoosePublisherDao, "get_by_channel", lambda _channel_id: [publisher])
    monkeypatch.setattr(
        goose_publisher_dao.GoosePublisherDao,
        "save_publisher",
        lambda channel_id, config: saved_publishers.append((channel_id, config)) or 9,
    )
    monkeypatch.setattr(goose_receiver_dao.GooseReceiverDao, "list_by_channel", lambda _channel_id: [receiver])

    publisher_calls = []
    receiver_calls = []
    manager = SimpleNamespace(
        create_publisher=lambda **kwargs: publisher_calls.append(kwargs) or {"is_running": False},
        create_receiver=lambda **kwargs: receiver_calls.append(kwargs) or {"is_running": False},
    )

    result = Iec61850CopyService.hydrate_runtime_resources(20, manager)

    assert result == {"publishers": 1, "receivers": 1}
    assert publisher_calls[0]["channel_id"] == 20
    assert publisher_calls[0]["skip_model_rebuild"] is True
    assert "start" not in publisher_calls[0]
    assert receiver_calls[0]["db_id"] == 8
    assert "start" not in receiver_calls[0]
    assert saved_publishers == [(20, publisher)]
