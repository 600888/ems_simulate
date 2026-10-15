"""GOOSE uses the device's loaded model and has its own MMS-independent lifecycle."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi import UploadFile
import pytest

from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler
from src.proto.iec61850.plugins.goose import manager as manager_module
from src.proto.iec61850.plugins.goose import publisher as publisher_module
from src.proto.iec61850.plugins.goose import subscriber as subscriber_module
from src.proto.iec61850.plugins.goose.client_control import GooseClientControl
from src.proto.iec61850.plugins.goose.persistence import PersistenceAdapter
from src.proto.iec61850.plugins.goose.subscriber import GooseReceiver
from src.proto.iec61850.plugins.goose.types import ReceiverConfig
from src.web.api.channel import goose, import_points
from src.web.api.exceptions import NotFoundError, OperationError
from src.web.api.schemas.goose import GoosePublisherCreate, GoosePublisherIdRequest, GooseSubscriptionUpdate

CB_REF = "IEDLD0/LLN0$GO$gcb1"
DS_REF = "IEDLD0/LLN0$ds1"
DATASETS = [
    {
        "ref": DS_REF,
        "members": [{"ref": "IEDLD0/GGIO1.Ind1.stVal", "fc": "ST", "b_type": "BOOLEAN"}],
    }
]


def _request(handler, manager=None):
    controller = SimpleNamespace(get_device_by_channel_id=lambda _: SimpleNamespace(protocol_handler=handler))
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(device_controller=controller, goose_manager=manager))
    )


@pytest.mark.parametrize("connected", [False, True])
@pytest.mark.asyncio
async def test_subscription_toggle_only_controls_local_reception(monkeypatch, connected):
    monkeypatch.setattr(subscriber_module, "HAS_IEC61850", True)
    receiver = GooseReceiver(ReceiverConfig(interface="test"))
    receiver.add_subscription(CB_REF, enabled=False)
    receiver.start = Mock(side_effect=lambda: setattr(receiver, "_is_running", True) or True)
    receiver.stop = Mock(side_effect=lambda: setattr(receiver, "_is_running", False))
    manager = manager_module.GooseResourceManager()
    manager._receivers["receiver"] = receiver
    manager._receiver_channel_map["receiver"] = 7
    monkeypatch.setattr(manager, "_persist_receiver", Mock())
    monkeypatch.setattr(goose, "_validate_iec61850_channel", Mock())
    remote_write = Mock(side_effect=AssertionError("local subscription must not change remote GoEna"))
    monkeypatch.setattr(GooseClientControl, "set_go_ena", remote_write)

    handler = IEC61850ClientHandler()
    handler._client = Mock(_conn=object() if connected else None)
    handler._is_running = connected
    handler._model_loaded = True
    handler._discovered_datasets = DATASETS
    handler._discovered_goose_items = [{"go_cb_ref": CB_REF, "data_set_ref": DS_REF}]
    handler._client.browse_dataset_directory.side_effect = AssertionError("loaded metadata must not require MMS")
    request = _request(handler, manager)
    body = GooseSubscriptionUpdate(channel_id=7, receiver_id="receiver", go_cb_ref=CB_REF, data_set_ref=DS_REF)

    enabled = await goose.update_receiver_subscription(request, body.model_copy(update={"enabled": True}))
    assert enabled.data["is_running"] is True
    assert enabled.data["subscriptions"][0]["enabled"] is True
    assert enabled.data["subscriptions"][0]["dataset_entries"] == [
        {"name": "IEDLD0/GGIO1.Ind1.stVal", "fc": "ST", "type": "boolean", "description": ""}
    ]

    # Closing MMS after discovery must retain both the model and active GOOSE.
    handler.disconnect()
    assert handler.model_loaded is True
    assert _get_candidates(handler)[0]["go_cb_ref"] == CB_REF
    assert receiver.is_running is True
    receiver.stop.assert_not_called()

    disabled = await goose.update_receiver_subscription(request, body)
    assert disabled.data["subscriptions"][0]["enabled"] is False
    # A stopped MMS association also permits enabling GOOSE again.
    enabled_again = await goose.update_receiver_subscription(request, body.model_copy(update={"enabled": True}))
    assert enabled_again.data["subscriptions"][0]["enabled"] is True
    remote_write.assert_not_called()
    handler._client.browse_dataset_directory.assert_not_called()


def _get_candidates(handler):
    return goose._get_discovered_goose(7, _request(handler))


def test_icd_server_dataset_metadata_is_available_before_mms_start():
    handler = IEC61850ServerHandler()
    handler._server = Mock(is_running=False)
    handler._server.browse_datasets.return_value = DATASETS
    assert goose._resolve_dataset_entries(_request(handler), 7, DS_REF.replace("$", "."), []) == [
        {"name": "IEDLD0/GGIO1.Ind1.stVal", "fc": "ST", "type": "boolean", "description": ""}
    ]
    handler._server.start.assert_not_called()


@pytest.mark.asyncio
async def test_publisher_can_start_with_mms_off_and_continue_after_mms_stops(monkeypatch):
    from src.web.api import network_interfaces

    monkeypatch.setattr(manager_module, "HAS_IEC61850", True)
    monkeypatch.setattr(publisher_module, "HAS_IEC61850", True)
    # Exercise the real Publisher lifecycle, replacing only Ethernet transmission.
    monkeypatch.setattr(publisher_module.GoosePublisher, "_create_publisher", Mock())
    monkeypatch.setattr(publisher_module.GoosePublisher, "publish", Mock(return_value=True))
    monkeypatch.setattr(publisher_module.GoosePublisher, "_retransmit_loop", lambda _: None)
    monkeypatch.setattr(goose, "_validate_iec61850_channel", Mock())
    monkeypatch.setattr(network_interfaces, "validate_network_interface", Mock())
    backend = SimpleNamespace(save_publisher=Mock(return_value=1))
    manager = manager_module.GooseResourceManager(PersistenceAdapter(backend))
    handler = IEC61850ServerHandler()
    server = Mock(is_running=False, model_loaded=True)
    handler._server = server
    request = _request(handler, manager)
    created = await goose.create_goose_publisher(
        request,
        GoosePublisherCreate(
            channel_id=7,
            interface="test",
            go_cb_ref=CB_REF,
            data_set_ref=DS_REF,
            entries=[{"name": "IEDLD0/GGIO1.Ind1.stVal", "value": True, "iec_type": "boolean"}],
        ),
    )
    body = GoosePublisherIdRequest(channel_id=7, publisher_id=created.data["id"])
    try:
        await goose.start_goose_publisher(body=body, request=request)
        assert manager.get_publisher_status(body.publisher_id)["is_running"] is True
        server.start.assert_not_called()

        # Starting/stopping MMS later must leave this Ethernet Publisher running.
        server.is_running = True
        handler._is_running = True
        assert await handler.stop() is True
        assert manager.get_publisher_status(body.publisher_id)["is_running"] is True
        assert manager.publish_now(body.publisher_id) is True
    finally:
        manager.stop_all()


@pytest.mark.asyncio
async def test_local_subscription_failure_is_reported_without_remote_write(monkeypatch):
    manager = Mock()
    manager.get_receiver_status.return_value = {"channel_id": 7}
    manager.update_subscription.return_value = None
    monkeypatch.setattr(goose, "_validate_iec61850_channel", Mock())
    body = GooseSubscriptionUpdate(channel_id=7, receiver_id="receiver", go_cb_ref=CB_REF, enabled=True)
    with pytest.raises(OperationError, match="GOOSE 订阅配置应用失败"):
        await goose.update_receiver_subscription(_request(None, manager), body)


@pytest.mark.asyncio
async def test_device_ownership_is_still_required(monkeypatch):
    manager = Mock()
    manager.get_receiver_status.return_value = {"channel_id": 8}
    monkeypatch.setattr(goose, "_validate_iec61850_channel", Mock())
    body = GooseSubscriptionUpdate(channel_id=7, receiver_id="receiver", go_cb_ref=CB_REF, enabled=True)
    with pytest.raises(NotFoundError):
        await goose.update_receiver_subscription(_request(None, manager), body)
    manager.update_subscription.assert_not_called()


@pytest.mark.parametrize("was_running", [False, True])
@pytest.mark.parametrize("mode", ["model_only", "local_publish", "remote_subscribe", "both"])
@pytest.mark.asyncio
async def test_icd_import_preserves_mms_state_with_goose_and_datasets(monkeypatch, tmp_path, was_running, mode):
    from src.proto.iec61850.plugins.goose import cleanup
    from src.proto.iec61850.plugins.scl.service.file_manager import SclFileManager
    from src.proto.iec61850.plugins.scl.service.import_service import SclImportService

    publisher = {
        "interface": "test",
        "go_cb_ref": CB_REF,
        "go_id": CB_REF,
        "data_set_ref": DS_REF,
        "app_id": 1,
        "conf_rev": 1,
        "time_allowed_to_live": 1000,
        "entries": [],
    }
    scl_result = SimpleNamespace(
        ied_name="IED",
        points=SimpleNamespace(yc_points=[], yx_points=[], yk_points=[], yt_points=[]),
        goose=SimpleNamespace(pure_datasets=[]),
        to_dict=lambda: {
            "goose": {
                "publishers": [publisher],
                "subscriptions": [{"go_cb_ref": CB_REF}],
                "engineered_subscriptions": [{"go_cb_ref": CB_REF, "binding_status": "resolved"}],
            },
            "report_controls": [{}],
        },
    )
    monkeypatch.setattr(SclImportService, "import_file", Mock(return_value=scl_result))
    monkeypatch.setattr(SclFileManager, "save_to_device_dir", Mock(return_value=str(tmp_path / "model.icd")))
    monkeypatch.setattr(SclFileManager, "compute_hash_from_file", Mock(return_value="hash"))
    monkeypatch.setattr(import_points, "get_storage_path", lambda _: str(tmp_path))
    monkeypatch.setattr(import_points, "require_iec61850_channel", Mock())
    monkeypatch.setattr(import_points.ChannelService, "get_channel_by_id", Mock(return_value={"name": "IED"}))
    monkeypatch.setattr(import_points.ChannelService, "update_channel", Mock())
    monkeypatch.setattr(import_points, "reload_device_instance", AsyncMock())
    monkeypatch.setattr(cleanup, "clear_channel_goose_resources", Mock(return_value={}))
    from src.data.dao.goose_publisher_dao import GoosePublisherDao

    monkeypatch.setattr(GoosePublisherDao, "save_pure_dataset", Mock(return_value=1))

    handler = IEC61850ServerHandler()
    server = Mock(is_running=False, _goose_cb_list=[], _dataset_catalog=DATASETS, _ld_map={}, _ln_map={})
    server.browse_datasets.return_value = DATASETS
    server.reports.rcb_list = [{}]
    server.start.side_effect = lambda **_: setattr(server, "is_running", True)
    handler._server = server
    manager = Mock()
    device = SimpleNamespace(protocol_handler=handler, is_protocol_running=lambda: was_running)
    controller = SimpleNamespace(get_device_by_channel_id=lambda _: device)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(device_controller=controller, goose_manager=manager))
    )

    response = await import_points.import_icd(
        request,
        channel_id=7,
        file=UploadFile(BytesIO(b"<SCL/>"), filename="model.icd"),
        interface="test",
        auto_create_goose=False,
        goose_import_mode=mode,
    )

    assert response.data["model_loaded"] is True
    assert response.data["goose"]["errors"] == []
    if was_running:
        server.start.assert_called_once_with(register_default_rcbs=False)
    else:
        server.start.assert_not_called()
    assert manager.create_publisher.call_count == int(mode in {"local_publish", "both"})
    assert manager.import_discovered.call_count == int(mode in {"remote_subscribe", "both"})
