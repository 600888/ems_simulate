"""GOOSE retransmission strategy and ndsCom configuration regression tests."""

from types import SimpleNamespace
from unittest.mock import Mock

from pydantic import ValidationError as PydanticValidationError
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.data.controller.db_controller import DbController
from src.data.dao import goose_publisher_dao
import src.data.model  # noqa: F401
from src.data.model.base import Base
from src.proto.iec61850.plugins.goose import manager as manager_module
from src.proto.iec61850.plugins.goose import publisher as publisher_module
from src.proto.iec61850.plugins.goose.capture import GooseCaptureEngine
from src.proto.iec61850.plugins.goose.persistence import PersistenceAdapter
from src.proto.iec61850.plugins.goose.publisher import GoosePublisher
from src.proto.iec61850.plugins.goose.types import GooseDataSetEntry, PublisherConfig
from src.web.api.channel import goose
from src.web.api.exceptions import ValidationError
from src.web.api.schemas.goose import GoosePublisherCreate, GoosePublisherUpdate

CB_REF = "TESTLD/LLN0$GO$gcb1"


@pytest.fixture(autouse=True)
def enable_goose(monkeypatch):
    monkeypatch.setattr(publisher_module, "HAS_IEC61850", True)
    monkeypatch.setattr(manager_module, "HAS_IEC61850", True)


def test_worker_grows_intervals_caps_and_resets_on_data_change(monkeypatch):
    publisher = GoosePublisher(
        PublisherConfig(retransmit_initial_ms=2, retransmit_multiplier=2.5, retransmit_final_ms=20)
    )
    publisher.add_entry(GooseDataSetEntry("stVal", False))
    publisher._is_running = True
    publisher._is_created = True
    publisher._publisher = object()
    publisher._uses_npcap_transport = True
    clock = [0.0]
    sends = []
    monkeypatch.setattr(publisher_module.time, "monotonic", lambda: clock[0])

    def send():
        sends.append((clock[0], publisher.st_num, publisher.sq_num))
        if len(sends) == 8:
            publisher._is_running = False
        return True

    changed = False

    def wait(timeout):
        nonlocal changed
        # Wake the worker during a final-interval wait with a data change.
        if len(sends) == 5 and not changed:
            changed = True
            clock[0] += 0.001
            assert publisher.update_entry(0, True)
        else:
            clock[0] += timeout

    monkeypatch.setattr(publisher, "_publish_with_npcap", send)
    monkeypatch.setattr(publisher._retransmit_condition, "wait", wait)
    assert publisher.publish()
    publisher._retransmit_loop()

    assert [item[0] for item in sends] == pytest.approx([0, 0.002, 0.007, 0.0195, 0.0395, 0.0405, 0.0425, 0.0475])
    assert [item[2] for item in sends] == [0, 1, 2, 3, 4, 0, 1, 2]
    assert sends[5][1] == sends[4][1] + 1


@pytest.mark.parametrize("needs_commissioning", [False, True])
def test_npcap_frame_carries_nds_com_and_tal_covers_next_interval(needs_commissioning):
    publisher = GoosePublisher(PublisherConfig(go_cb_ref=CB_REF, needs_commissioning=needs_commissioning))
    publisher._sq_num = 10
    publisher._retransmit_interval = 5
    payload = publisher._build_goose_payload()
    capture = GooseCaptureEngine(interface="test")
    capture._process_packet(bytes.fromhex("010ccd010001 020304050607 88b8") + payload)
    packet = capture.get_packets()[0]
    assert packet["nds_com"] is needs_commissioning
    assert packet["time_allowed_to_live"] == 10000


@pytest.mark.parametrize("needs_commissioning", [False, True])
def test_native_publisher_sets_needs_commissioning(monkeypatch, needs_commissioning):
    setter = Mock()
    native = object()
    monkeypatch.setattr(publisher_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        publisher_module,
        "iec61850",
        SimpleNamespace(GoosePublisher_create=lambda *_: native, GoosePublisher_setNeedsCommission=setter),
        raising=False,
    )
    publisher = GoosePublisher(PublisherConfig(needs_commissioning=needs_commissioning))
    monkeypatch.setattr(publisher, "_create_comm_parameters", lambda: None)
    publisher._create_publisher()
    setter.assert_called_once_with(native, needs_commissioning)


def test_failed_send_does_not_advance_strategy_or_sequence(monkeypatch):
    publisher = GoosePublisher(PublisherConfig())
    publisher._is_running = True
    publisher._is_created = True
    publisher._publisher = object()
    publisher._uses_npcap_transport = True
    monkeypatch.setattr(publisher, "_publish_with_npcap", lambda: False)
    assert publisher.publish() is False
    assert publisher.sq_num == 0
    assert publisher._next_retransmit_at == 0
    assert publisher._retransmit_interval == 0.002


@pytest.mark.parametrize(
    "values",
    [
        {"retransmit_initial_ms": 0},
        {"retransmit_initial_ms": 10, "retransmit_final_ms": 2},
        {"retransmit_final_ms": 60001},
        {"retransmit_multiplier": 0.5},
        {"retransmit_multiplier": float("nan")},
        {"retransmit_multiplier": float("inf")},
    ],
)
def test_invalid_strategies_are_rejected(values):
    with pytest.raises(ValueError):
        PublisherConfig(**values)
    with pytest.raises(PydanticValidationError):
        GoosePublisherCreate(go_cb_ref=CB_REF, **values)


@pytest.mark.asyncio
async def test_api_create_update_persistence_and_runtime_reload(monkeypatch):
    from src.web.api import network_interfaces

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(goose_publisher_dao, "local_session", sessionmaker(engine, expire_on_commit=False))
    monkeypatch.setattr(goose, "_validate_iec61850_channel", Mock())
    monkeypatch.setattr(network_interfaces, "validate_network_interface", Mock())
    manager = manager_module.GooseResourceManager()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(goose_manager=manager)))
    values = dict(
        retransmit_initial_ms=4, retransmit_multiplier=1.5, retransmit_final_ms=3000, needs_commissioning=True
    )
    created = await goose.create_goose_publisher(
        request, GoosePublisherCreate(channel_id=7, interface="test", go_cb_ref=CB_REF, **values)
    )
    publisher_id = created.data["id"]
    for key, value in values.items():
        assert created.data[key] == value
    await goose.update_goose_publisher(
        request,
        GoosePublisherUpdate(
            channel_id=7, publisher_id=publisher_id, retransmit_multiplier=3, needs_commissioning=False
        ),
    )
    values.update(retransmit_multiplier=3, needs_commissioning=False)
    # A partial update must also be checked against the retained Initial.
    with pytest.raises(ValidationError):
        await goose.update_goose_publisher(
            request, GoosePublisherUpdate(channel_id=7, publisher_id=publisher_id, retransmit_final_ms=2)
        )
    config = goose_publisher_dao.GoosePublisherDao.get_by_channel(7)[0]
    restored = manager_module.GooseResourceManager(PersistenceAdapter(SimpleNamespace(save_publisher=Mock())))
    config.pop("_db_id")
    config.pop("_channel_id")
    for key in ("name", "description", "auto_start"):
        config.pop(key)
    status = restored.create_publisher(channel_id=7, **config)
    for key, value in values.items():
        assert status[key] == value
    engine.dispose()


def test_existing_database_gets_defaults_and_migration_is_idempotent():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE goose_publisher (id INTEGER PRIMARY KEY, go_cb_ref TEXT)"))
        conn.execute(text("INSERT INTO goose_publisher VALUES (1, 'existing')"))
    controller = DbController()
    controller.db_config = SimpleNamespace(engine=engine)
    controller._migrate_goose_schema()
    controller._migrate_goose_schema()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM goose_publisher")).mappings().one()
        assert row["go_cb_ref"] == "existing"
        assert row["retransmit_initial_ms"] == 2
        assert row["retransmit_multiplier"] == 2
        assert row["retransmit_final_ms"] == 5000
        assert row["needs_commissioning"] == 0
    engine.dispose()
