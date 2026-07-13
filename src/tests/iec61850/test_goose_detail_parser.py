from src.device.core.message.parsers.goose import parse_goose
from src.proto.iec61850.plugins.goose import detail as detail_module


def _tlv(tag: int, value: bytes) -> bytes:
    return bytes((tag, len(value))) + value


def _frame() -> bytes:
    fields = b"".join(
        [
            _tlv(0x80, b"LD0/LLN0$GO$gcb1"),
            _tlv(0x81, b"\x03\xe8"),
            _tlv(0x82, b"LD0/LLN0$dsGOOSE1"),
            _tlv(0x83, b"gcb1"),
            _tlv(0x85, b"\x01"),
            _tlv(0x86, b"\x00"),
            _tlv(0x87, b"\x00"),
            _tlv(0x88, b"\x01"),
            _tlv(0x89, b"\x00"),
            _tlv(0x8A, b"\x02"),
            _tlv(0xAB, _tlv(0x83, b"\x01") + _tlv(0x85, b"\xff")),
        ]
    )
    pdu = _tlv(0x61, fields)
    ethernet = bytes.fromhex("010ccd010001 020304050607 88b8")
    goose_length = len(pdu) + 8
    header = bytes.fromhex("0001") + goose_length.to_bytes(2, "big") + bytes(4)
    return ethernet + header + pdu


def test_goose_parser_maps_dataset_items_to_original_frame_bytes():
    raw = _frame()
    detail = parse_goose(raw)

    assert detail["valid"] is True
    assert detail["raw_hex"]
    assert detail["go_cb_ref"] == "LD0/LLN0$GO$gcb1"
    assert [item["value"] for item in detail["objects"]] == [True, -1]
    for item in detail["objects"]:
        assert bytes.fromhex(item["raw_value"]) == raw[item["offset"] : item["offset"] + item["length"]]


def test_goose_detail_enrichment_links_dataset_entry_and_point(monkeypatch):
    parsed = parse_goose(_frame())
    packet = {
        "go_cb_ref": parsed["go_cb_ref"],
        "data_set_ref": parsed["data_set_ref"],
        "data_values": parsed["objects"],
    }
    receivers = [
        {
            "subscriptions": [
                {
                    "go_cb_ref": parsed["go_cb_ref"],
                    "dataset_entries": [
                        {"name": "LD0/XCBR1.Pos.stVal", "fc": "ST", "description": "断路器位置"},
                        {"name": "LD0/MMXU1.A.phsA.cVal.mag.i", "fc": "MX"},
                    ],
                }
            ]
        }
    ]
    points = [
        {
            "reg_addr": "LD0/XCBR1.Pos.stVal",
            "code": "XCBR_POS",
            "name": "断路器位置",
            "frame_type": 1,
            "fc": "ST",
        }
    ]
    monkeypatch.setattr(detail_module, "_load_channel_metadata", lambda _channel_id: (receivers, [], points))

    enriched = detail_module.enrich_goose_packet(packet, 1)

    assert enriched["data_values"][0]["name"] == "LD0/XCBR1.Pos.stVal"
    assert enriched["data_values"][0]["point"]["code"] == "XCBR_POS"
    assert enriched["data_values"][0]["offset"] == parsed["objects"][0]["offset"]


def test_goose_detail_uses_publisher_entries_and_app_id_fallback(monkeypatch):
    parsed = parse_goose(_frame())
    packet = {
        "app_id": 1,
        "go_cb_ref": "different-format",
        "data_set_ref": "",
        "data_values": parsed["objects"],
    }
    publishers = [
        {
            "go_cb_ref": "LD0/LLN0$GO$gcb1",
            "app_id": 1,
            "entries": [{"name": "LD0/XCBR1.Pos.stVal", "iec_type": "boolean"}],
        }
    ]
    monkeypatch.setattr(detail_module, "_load_channel_metadata", lambda _channel_id: ([], publishers, []))

    enriched = detail_module.enrich_goose_packet(packet, 1)

    assert enriched["data_values"][0]["name"] == "LD0/XCBR1.Pos.stVal"
    assert enriched["data_values"][0]["dataset_type"] == "boolean"
