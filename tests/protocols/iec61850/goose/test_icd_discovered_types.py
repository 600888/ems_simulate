"""Preserve vendor ICD member types through the discovered-GOOSE API."""

from pathlib import Path
from types import SimpleNamespace

from src.device.protocol.iec61850_handler import IEC61850ClientHandler
from src.proto.iec61850.iec61850_client import IEC61850Client
from src.proto.iec61850.plugins.goose.capture import GooseCaptureEngine
from src.proto.iec61850.plugins.goose.manager import GooseResourceManager
from src.web.api.channel.goose import _get_discovered_goose

_ICD = Path(__file__).resolve().parents[3] / "fixtures/iec61850/HOPEWIND_PCS2500_GOOSE.icd"
_TYPES = ["float"] * 5 + ["integer"] + ["float"] * 4


def test_client_icd_import_preserves_discovered_goose_and_dataset_types():
    client = IEC61850Client(model_name="TEMPLATE")
    handler = IEC61850ClientHandler()
    handler._client = client
    try:
        assert handler.load_model_from_icd(str(_ICD))
        controller = SimpleNamespace(get_device_by_channel_id=lambda _: SimpleNamespace(protocol_handler=handler))
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(device_controller=controller)))
        items = _get_discovered_goose(1, request)
        assert len(items) == 1
        entries = items[0]["dataset_entries"]
        assert [entry["type"] for entry in entries] == _TYPES
        assert entries[5]["name"] == "TEMPLATEPIGO/GOOUTGGIO1.AnIn6.instMag.i"
        dataset = handler.get_discovered_datasets()[0]
        assert [member["iec_type"] for member in dataset["members"]] == _TYPES

        # Exercise the publisher path used by "add discovered as publisher",
        # then inspect the encoded frame without sending it to a network.
        manager = GooseResourceManager()
        status = manager.create_publisher(
            interface="test",
            go_cb_ref=items[0]["go_cb_ref"],
            data_set_ref=items[0]["data_set_ref"],
            entries=[
                {"name": entry["name"], "iec_type": entry["type"], "value": -123 if index == 5 else 12.5}
                for index, entry in enumerate(entries)
            ],
        )
        assert status is not None
        assert [entry["iec_type"] for entry in status["entries"]] == _TYPES
        publisher = manager._publishers[status["id"]]
        frame = bytes.fromhex("010ccd010001 020304050607 88b8") + publisher._build_goose_payload()
        capture = GooseCaptureEngine(interface="test")
        capture._process_packet(frame)
        values = capture.get_packets()[0]["data_values"]
        assert [entry["type"] for entry in values] == _TYPES
        assert [entry["value"] for entry in values] == [12.5] * 5 + [-123] + [12.5] * 4

        # Older in-memory candidates had b_type but no scalar iec_type.
        for member in handler._discovered_goose_items[0]["dataset_members"]:
            member.pop("iec_type")
        legacy_items = _get_discovered_goose(1, request)
        assert [entry["type"] for entry in legacy_items[0]["dataset_entries"]] == _TYPES
    finally:
        client.disconnect()
