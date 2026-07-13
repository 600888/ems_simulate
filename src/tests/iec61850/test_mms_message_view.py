from types import SimpleNamespace

from src.device.core.message.message_formatter import MessageFormatter
from src.device.core.message.mms_capture import MmsMessageCapture
from src.device.core.message.parsers.mms import parse_mms
from src.enums.modbus_def import ProtocolType


def _tpkt(payload: bytes) -> bytes:
    frame = b"\x03\x00\x00\x00\x02\xf0\x80" + payload
    return frame[:2] + len(frame).to_bytes(2, "big") + frame[4:]


def test_parse_confirmed_mms_read_request():
    raw = _tpkt(bytes.fromhex("A0 07 02 01 05 A4 02 30 00"))

    detail = parse_mms(raw, role="Request")

    assert detail["valid"] is True
    assert detail["protocol"] == "IEC 61850 MMS"
    assert detail["frame_kind"] == "Confirmed-RequestPDU"
    assert "Read" in detail["summary"]
    assert "Invoke ID=5" in detail["summary"]
    assert next(field for field in detail["fields"] if field["key"] == "mms_service")["value"] == "Read"


def test_parse_confirmed_mms_response_data_value():
    raw = _tpkt(bytes.fromhex("A1 0A 02 01 05 A4 05 A1 03 83 01 FF"))

    detail = parse_mms(raw, role="Response")

    assert detail["frame_kind"] == "Confirmed-ResponsePDU"
    assert detail["objects"][0]["name"] == "Boolean"
    assert detail["objects"][0]["value"] is True


def test_mms_capture_reassembles_and_splits_tpkt_frames():
    first = _tpkt(bytes.fromhex("A0 07 02 01 01 A4 02 30 00"))
    second = _tpkt(bytes.fromhex("A0 07 02 01 02 A4 02 30 00"))
    capture = MmsMessageCapture(port=102, remote_ip="192.0.2.10", client=True)
    key = ("192.0.2.20", 50000, "192.0.2.10", 102)

    capture._accept_segment(key, 1000, first[:8], "TX")
    assert capture.get_messages() == []
    capture._accept_segment(key, 1008, first[8:] + second, "TX")

    messages = capture.get_messages()
    assert [message["direction"] for message in messages] == ["TX", "TX"]
    assert [message["data"] for message in messages] == [first.hex(), second.hex()]


def test_formatter_exposes_mms_list_and_detail():
    raw = _tpkt(bytes.fromhex("A0 07 02 01 07 A4 02 30 00"))
    handler = SimpleNamespace(
        get_captured_messages=lambda _limit: [
            {
                "sequence_id": 1,
                "direction": "TX",
                "data": raw.hex(),
                "hex_string": " ".join(f"{byte:02x}" for byte in raw),
                "timestamp": 1.0,
                "time": "2026-07-13 12:00:00.000",
                "length": len(raw),
            }
        ]
    )
    device = SimpleNamespace(
        protocol_handler=handler,
        protocol_type=ProtocolType.Iec61850Client,
        point_manager=SimpleNamespace(get_all_points=lambda: []),
    )
    formatter = MessageFormatter(device)

    messages = formatter.get_messages()
    detail = formatter.get_message_detail(1)

    assert messages[0]["msg_type"] == "Request"
    assert "Read" in messages[0]["description"]
    assert detail is not None
    assert detail["sequence_id"] == 1
    assert detail["frame_kind"] == "Confirmed-RequestPDU"
