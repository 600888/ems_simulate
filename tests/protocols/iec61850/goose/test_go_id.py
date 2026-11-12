"""GoID must survive import, discovery and packet encoding independently of GoCBRef."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import UploadFile
import pytest

from src.device.protocol.iec61850_handler import IEC61850ClientHandler
from src.proto.iec61850.iec61850_client import IEC61850Client
from src.proto.iec61850.plugins.datasets import server as dataset_server_module
from src.proto.iec61850.plugins.goose.capture import GooseCaptureEngine
from src.proto.iec61850.plugins.goose.publisher import GoosePublisher
from src.proto.iec61850.plugins.goose.types import PublisherConfig
from src.proto.iec61850.plugins.scl.service.import_service import SclImportService
from src.proto.iec61850.plugins.scl.transformer.server_model_builder import SclServerModelBuilder
from src.tools.icd_goose_importer import import_goose_from_icd
from src.web.api.channel import import_points
from src.web.api.channel.goose import _get_discovered_goose
from src.web.api.scl import router as scl_router

CB_REF = "TEMPLATEPIGO/LLN0$GO$gocb1"
GO_ID = "TEMPLATERPIT/LLN0.gocb1"


def _scl(go_id):
    attribute = f'appID="{go_id}"' if go_id else ""
    return f"""<SCL>
      <Communication><SubNetwork name="station"><ConnectedAP iedName="IED" apName="AP">
        <GSE ldInst="TEMPLATEPIGO" cbName="gocb1"><Address>
          <P type="APPID">2001</P>
        </Address></GSE>
      </ConnectedAP></SubNetwork></Communication>
      <IED name="IED"><AccessPoint name="AP"><Server><LDevice inst="TEMPLATEPIGO">
        <LN0 lnClass="LLN0" lnType="Common">
          <DataSet name="dsGOOSE1"/>
          <GSEControl {attribute} confRev="1" datSet="dsGOOSE1" desc="GOOSE发布" name="gocb1" type="GOOSE"/>
        </LN0>
      </LDevice></Server></AccessPoint></IED>
      <DataTypeTemplates><LNodeType id="Common" lnClass="LLN0"/></DataTypeTemplates>
    </SCL>"""


@pytest.mark.parametrize("go_id", ["TripSignal", GO_ID, "1001", "", CB_REF])
def test_scl_import_and_server_model_preserve_configured_go_id(tmp_path, go_id):
    result = SclImportService().import_string(_scl(go_id), validate=False)
    goose = result.to_dict()["goose"]
    model = SclServerModelBuilder(result.doc).build()
    control = model.lds[0].lns[0].gocb_list[0]

    assert control.go_cb_ref == CB_REF
    assert control.go_id == go_id
    assert goose["summary"]["gse_controls"][0]["go_id"] == go_id
    for item in [goose["publishers"][0], goose["subscriptions"][0]]:
        assert item["go_cb_ref"] == CB_REF
        assert item["go_id"] == go_id
        assert item["app_id"] == 0x2001

    path = tmp_path / "goose.icd"
    path.write_text(_scl(go_id), encoding="utf-8")
    legacy = import_goose_from_icd(str(path))
    assert legacy["summary"]["gse_controls"][0]["go_id"] == go_id
    assert legacy["publishers"][0]["go_id"] == go_id
    assert legacy["publishers"][0]["app_id"] == 0x2001
    assert legacy["subscriptions"][0]["go_id"] == go_id


@pytest.mark.parametrize("go_id", ["TripSignal", GO_ID, "", CB_REF])
def test_discovery_preserves_remote_go_id_without_changing_cached_metadata(go_id):
    raw = {"go_cb_ref": CB_REF, "go_id": go_id}
    handler = SimpleNamespace(_discovered_goose_items=[raw])
    controller = SimpleNamespace(get_device_by_channel_id=lambda _: SimpleNamespace(protocol_handler=handler))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(device_controller=controller)))

    assert _get_discovered_goose(7, request)[0]["go_id"] == go_id
    assert raw == {"go_cb_ref": CB_REF, "go_id": go_id}


def test_encoded_goose_keeps_go_id_distinct_from_control_block_reference():
    result = SclImportService().import_string(_scl(GO_ID), validate=False)
    config = result.goose.gse_controls[0].to_publisher_dict()
    publisher = GoosePublisher(
        PublisherConfig(go_cb_ref=config["go_cb_ref"], go_id=config["go_id"], app_id=config["app_id"])
    )
    capture = GooseCaptureEngine(interface="test")
    capture._process_packet(bytes.fromhex("010ccd012001 020304050607 88b8") + publisher._build_goose_payload())

    packet = capture.get_packets()[0]
    assert packet["go_cb_ref"] == CB_REF
    assert packet["go_id"] == GO_ID
    assert packet["app_id"] == 0x2001


@pytest.mark.parametrize("go_id", [GO_ID, ""])
def test_native_mms_registration_uses_go_id_instead_of_numeric_app_id(monkeypatch, go_id):
    result = SclImportService().import_string(_scl(go_id), validate=False)
    calls = []
    monkeypatch.setattr(
        dataset_server_module,
        "iec61850",
        SimpleNamespace(GSEControlBlock_create=lambda *args: calls.append(args) or object()),
        raising=False,
    )
    lln0 = object()
    builder = SimpleNamespace(model=object(), ln_map={"TEMPLATEPIGO/LLN0": lln0}, keep_alive=[])
    manager = dataset_server_module.ServerDataSetManager(builder)
    manager.dataset_catalog.append({"ref": "TEMPLATEPIGO/LLN0$dsGOOSE1"})
    config = result.goose.gse_controls[0].to_publisher_dict()
    manager.pending_registrations.append({**config, "_type": "gocb"})

    manager.apply_pending_registrations(manager.add_goose_control_block, manager.register_dataset)

    assert len(calls) == 1
    assert calls[0][:5] == ("gocb1", lln0, go_id, "dsGOOSE1", 1)
    assert manager.goose_cb_list[0]["app_id"] == 0x2001


@pytest.mark.asyncio
async def test_upload_preview_returns_exact_scl_go_id(monkeypatch, tmp_path):
    monkeypatch.setattr(import_points, "get_storage_path", lambda _: str(tmp_path))
    file = UploadFile(BytesIO(_scl(GO_ID).encode("utf-8")), filename="goose.icd")

    response = await import_points.preview_icd(None, file=file, interface="eth-test")

    goose = response.data["goose"]
    assert goose["errors"] == []
    assert goose["summary"]["gse_controls"][0]["go_id"] == GO_ID
    assert goose["publishers"][0]["go_id"] == GO_ID
    assert goose["subscriptions"][0]["go_id"] == GO_ID


@pytest.mark.asyncio
async def test_scl_import_api_returns_exact_scl_go_id(monkeypatch, tmp_path):
    path = tmp_path / "goose.icd"
    path.write_text(_scl(GO_ID), encoding="utf-8")
    monkeypatch.setattr(scl_router, "require_iec61850_channel", lambda _: None)
    monkeypatch.setattr(scl_router, "_get_scl_file_path", lambda *_: str(path))
    monkeypatch.setattr(scl_router, "_get_import_service", lambda _: SclImportService())

    response = await scl_router.import_goose_from_scl(None, channel_id=7, filename="goose.icd", interface="eth-test")

    assert response.data["summary"]["gse_controls"][0]["go_id"] == GO_ID
    assert response.data["publishers"][0]["go_id"] == GO_ID
    assert response.data["subscriptions"][0]["go_id"] == GO_ID


@pytest.mark.parametrize("reuse_parse_result", [False, True])
def test_client_icd_loading_keeps_go_id_in_handler_and_discovered_api(tmp_path, reuse_parse_result):
    path = tmp_path / "goose.icd"
    path.write_text(_scl(GO_ID), encoding="utf-8")
    result = SclImportService().import_file(str(path)) if reuse_parse_result else None
    handler = IEC61850ClientHandler()
    handler._client = IEC61850Client()

    assert handler.load_model_from_icd(str(path), scl_result=result)
    assert handler._client._discovered_goose_items[0]["go_id"] == GO_ID
    assert handler._discovered_goose_items[0]["go_id"] == GO_ID
    controller = SimpleNamespace(get_device_by_channel_id=lambda _: SimpleNamespace(protocol_handler=handler))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(device_controller=controller)))
    discovered = _get_discovered_goose(7, request)[0]
    assert discovered["go_cb_ref"] == CB_REF
    assert discovered["go_id"] == GO_ID
    assert discovered["app_id"] == 0x2001


@pytest.mark.parametrize("mode", ["model_only", "local_publish"])
@pytest.mark.asyncio
async def test_icd_upload_with_real_client_model_keeps_go_id_in_discovered_cache(monkeypatch, tmp_path, mode):
    from src.data.dao.goose_publisher_dao import GoosePublisherDao
    from src.proto.iec61850.plugins.goose import cleanup
    from src.proto.iec61850.plugins.scl.service.file_manager import SclFileManager

    handler = IEC61850ClientHandler()
    handler._client = IEC61850Client()
    device = SimpleNamespace(protocol_handler=handler, is_protocol_running=lambda: False)
    controller = SimpleNamespace(get_device_by_channel_id=lambda _: device)
    manager = Mock()
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(device_controller=controller, goose_manager=manager))
    )

    async def reload_client_model(_controller, _channel_id, *, is_start, scl_result):
        assert is_start is False
        assert handler.load_model_from_icd("uploaded.icd", scl_result=scl_result)

    monkeypatch.setattr(import_points, "get_storage_path", lambda _: str(tmp_path))
    monkeypatch.setattr(import_points, "require_iec61850_channel", lambda _: None)
    monkeypatch.setattr(import_points.ChannelService, "get_channel_by_id", lambda _: {"name": "IED"})
    monkeypatch.setattr(import_points.ChannelService, "update_channel", Mock())
    monkeypatch.setattr(import_points, "reload_device_instance", reload_client_model)
    monkeypatch.setattr(SclFileManager, "save_to_device_dir", Mock(return_value=str(tmp_path / "saved.icd")))
    monkeypatch.setattr(SclFileManager, "compute_hash_from_file", Mock(return_value="hash"))
    monkeypatch.setattr(cleanup, "clear_channel_goose_resources", Mock(return_value={}))
    monkeypatch.setattr(GoosePublisherDao, "save_pure_dataset", Mock(return_value=1))

    response = await import_points.import_icd(
        request,
        channel_id=7,
        file=UploadFile(BytesIO(_scl(GO_ID).encode("utf-8")), filename="goose.icd"),
        interface="eth-test",
        auto_create_goose=False,
        goose_import_mode=mode,
    )

    assert response.data["goose"]["errors"] == []
    assert response.data["goose"]["publishers"][0]["go_id"] == GO_ID
    assert _get_discovered_goose(7, request)[0]["go_id"] == GO_ID
    if mode == "local_publish":
        assert manager.create_publisher.call_args.kwargs["go_id"] == GO_ID
    else:
        manager.create_publisher.assert_not_called()
