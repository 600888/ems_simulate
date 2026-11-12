"""GOOSE descriptions follow the device's DataModel dU without MMS reads."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler
from src.proto.iec61850.core.registry import PointRegistry
from src.proto.iec61850.model.ied_model import DARef, DORef, IedModel, LDModel, LNModel
from src.proto.iec61850.plugins.datasets.metadata import build_description_index, description_for_ref
from src.web.api.channel import goose
from src.web.api.schemas.goose import GooseChannelRequest, GooseSubscriptionHistoryRequest


def test_description_uses_owning_do_and_explicit_du_with_exact_scope():
    descriptions = build_description_index(
        [
            {"address": "LD0/GGIO1.Ind1.stVal", "name": "旧描述", "code": "ind"},
            {"address": "LD0/GGIO1.Ind1.dU", "value": "开关位置"},
            {"address": "LD0/GGIO2.Ind1.stVal", "name": "其他节点", "code": "other"},
            {"address": "LD1/GGIO1.Ind1.stVal", "name": "其他设备", "code": "other"},
            {"address": "LD0/GGIO1.Ind10.stVal", "name": "Ind10", "code": "ind10"},
            {"address": "LD0/MMXU1.A.phsA.dU", "value": "A相电流"},
        ]
    )

    for ref in ("LD0/GGIO1.Ind1", "LD0/GGIO1.Ind1.stVal", "LD0/GGIO1$ST$Ind1$q[ST]"):
        assert description_for_ref(ref, descriptions) == "开关位置"
    assert description_for_ref("LD0/GGIO2.Ind1.q", descriptions) == "其他节点"
    assert description_for_ref("LD1/GGIO1.Ind1.t", descriptions) == "其他设备"
    assert description_for_ref("LD0/GGIO1.Ind10.stVal", descriptions) == ""
    assert description_for_ref("LD0/GGIO1.Ind100.stVal", descriptions) == ""
    assert description_for_ref("LD0/MMXU1.A.phsA.cVal.mag.f", descriptions) == "A相电流"


def test_generated_point_names_do_not_become_descriptions():
    address = "LD0/MMXU1.TotW.mag.f"
    for name, code in ((address, "w"), ("MMXU1.TotW.mag.f", "w"), ("TotW", "w"), ("w", "w")):
        assert build_description_index([{"address": address, "name": name, "code": code}]) == {}


def _request(handler, manager, *, description="实时描述"):
    point = SimpleNamespace(address="LD0/GGIO1.Ind1.stVal", name=description, code="position", fc="ST")
    device = SimpleNamespace(protocol_handler=handler, point_manager=SimpleNamespace(get_all_points=lambda: [point]))
    controller = SimpleNamespace(get_device_by_channel_id=lambda channel_id: device if channel_id == 7 else None)
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(device_controller=controller, goose_manager=manager))
    )


@pytest.mark.asyncio
async def test_existing_publisher_subscriber_and_history_follow_live_datamodel(monkeypatch):
    monkeypatch.setattr(goose, "_validate_iec61850_channel", Mock())
    handler = IEC61850ServerHandler()
    handler._server = SimpleNamespace(scl_model=None, _du_descriptions={}, browse_datasets=lambda: [])
    entry = {"name": "LD0/GGIO1.Ind1.stVal", "description": "", "value": True}
    manager = Mock()
    manager.list_publishers.return_value = [{"entries": [dict(entry)]}]
    manager.list_receivers.return_value = [
        {"subscriptions": [{"dataset_entries": [dict(entry)], "data_values": [dict(entry)]}]}
    ]
    manager.get_receiver_status.return_value = {"channel_id": 7}
    manager.get_subscription_history.return_value = [{"data_values": [dict(entry)]}]
    request = _request(handler, manager)
    body = GooseChannelRequest(channel_id=7)

    publishers = await goose.list_goose_publishers(body, request)
    receivers = await goose.list_goose_receivers(body, request)
    history = await goose.get_receiver_subscription_history(
        request, GooseSubscriptionHistoryRequest(channel_id=7, receiver_id="rx", go_cb_ref="LD0/LLN0$GO$gcb")
    )

    assert publishers.data["items"][0]["entries"][0]["description"] == "实时描述"
    assert publishers.data["items"][0]["entries"][0]["fc"] == "ST"
    subscription = receivers.data["items"][0]["subscriptions"][0]
    assert subscription["dataset_entries"][0]["description"] == "实时描述"
    assert subscription["data_values"][0]["description"] == "实时描述"
    assert history.data["items"][0]["data_values"][0]["description"] == "实时描述"
    assert manager.list_publishers.return_value[0]["entries"][0]["description"] == ""
    # Identical references from a different channel cannot use channel 7's dU.
    assert goose._enrich_model_descriptions(request, 8, [entry])[0]["description"] == ""


def test_offline_registry_references_and_stored_server_du():
    handler = IEC61850ClientHandler()
    registry = PointRegistry()
    registry.set_ref("LD0/GGIO1.Ind1.stVal", "IEDLD0/GGIO1.Ind1.stVal")
    registry.set_name("LD0/GGIO1.Ind1.stVal", "缓存描述")
    handler._client = SimpleNamespace(model=None, _registry=registry, _conn=None)
    entry = {"name": "IEDLD0/GGIO1$ST$Ind1$q", "description": ""}
    request = _request(handler, None)

    assert goose._enrich_model_descriptions(request, 7, [entry])[0]["description"] == "缓存描述"

    server_handler = IEC61850ServerHandler()
    server_handler._server = SimpleNamespace(
        scl_model=None, _du_descriptions={"LD0/GGIO1.Ind1": "模型dU"}, browse_datasets=lambda: []
    )
    assert (
        goose._enrich_model_descriptions(_request(server_handler, None), 7, [{"name": "LD0/GGIO1.Ind1.q"}])[0][
            "description"
        ]
        == "模型dU"
    )


def test_configured_subscription_entries_are_enriched_without_reimport():
    handler = IEC61850ServerHandler()
    handler._server = SimpleNamespace(scl_model=None, _du_descriptions={}, browse_datasets=lambda: [])
    configured = [{"name": "LD0/GGIO1.Ind1.q", "description": ""}]
    result = goose._resolve_dataset_entries(_request(handler, None), 7, "LD0/LLN0$ds", configured)
    assert result[0]["description"] == "实时描述"
    assert configured[0]["description"] == ""


def test_fc_comes_from_dataset_members_including_do_and_ambiguous_fc():
    handler = IEC61850ClientHandler()
    ref = "LD0/GGIO1.Ind1"
    handler._discovered_datasets = [
        {"ref": "LD0/LLN0$ds", "members": [{"ref": ref, "fc": "ST"}, {"ref": ref, "fc": "MX"}]}
    ]
    payload = {
        "data_set_ref": "LD0/LLN0.ds",
        "entries": [{"name": ref}, {"name": ref}],
    }
    result = goose._enrich_model_descriptions(_request(handler, None), 7, payload)
    assert [entry["fc"] for entry in result["entries"]] == ["ST", "MX"]
    assert "fc" not in payload["entries"][0]


def test_unregistered_quality_fc_uses_model_and_description_uses_current_point_name():
    handler = IEC61850ClientHandler()
    model = IedModel(
        lds=(
            LDModel(
                name="LD0",
                lns=(
                    LNModel(
                        name="GGIO1",
                        dos=(DORef(name="Ind1", ref="LD0/GGIO1.Ind1", das=(DARef(name="q", path="q", fc="ST"),)),),
                    ),
                ),
            ),
        ),
        _point_refs={"LD0/GGIO1.Ind1.stVal": {"name": "旧缓存描述", "fc": "ST"}},
    )
    handler._client = SimpleNamespace(model=model)
    result = goose._enrich_model_descriptions(_request(handler, None), 7, [{"name": "LD0/GGIO1.Ind1.q"}])
    assert result[0]["fc"] == "ST"
    assert result[0]["description"] == "实时描述"
