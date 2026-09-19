from types import SimpleNamespace

from pydnp3_pure.link.frame import LinkFrame
from pydnp3_pure.transport.segmenter import Segmenter
import pytest

from src.device.core.message.message_formatter import MessageFormatter
from src.device.core.message.parsers.dnp3 import _crc16_dnp3, parse_dnp3
from src.enums.modbus_def import ProtocolType
from src.proto.dnp3.wire import FragmentCorrelator

LINK_STATUS_REQUEST = bytes.fromhex("05 64 05 C9 01 00 00 00 DE 8E")


def _frame(control: int, data: bytes = b"") -> bytes:
    return LinkFrame.create(
        destination=1,
        source=0,
        primary=bool(control & 0x40),
        function=control & 0x0F,
        user_data=data,
        direction=bool(control & 0x80),
        fcb=bool(control & 0x20),
        fcv=bool(control & 0x10),
    ).serialize()


def test_reported_link_status_request_is_complete_valid_and_recognized():
    detail = parse_dnp3(LINK_STATUS_REQUEST)
    assert detail["summary"] == "请求链路状态 (REQUEST_LINK_STATUS)"
    assert detail["frame_kind"] == "链路控制帧"
    assert detail["purpose"] == "主站→从站"
    assert detail["valid"] is True
    assert detail["complete"] is True
    fields = {field["key"]: field for field in detail["fields"]}
    assert fields["dest_address"]["value"] == 1
    assert fields["src_address"]["value"] == 0
    assert fields["header_crc"]["raw_hex"] == "DE 8E"
    assert fields["header_crc"]["offset"] == 8
    assert "transport_control" not in fields
    assert "app_control" not in fields
    assert not detail["objects"]
    assert not detail["errors"]


@pytest.mark.parametrize(
    ("control", "name"),
    [
        (0x40, "RESET_LINK_STATES"),
        (0x52, "TEST_LINK_STATES"),
        (0x49, "REQUEST_LINK_STATUS"),
        (0x00, "ACK"),
        (0x01, "NACK"),
        (0x0B, "LINK_STATUS"),
        (0x0F, "NOT_SUPPORTED"),
    ],
)
@pytest.mark.parametrize("direction", [0, 0x80])
def test_link_control_summaries_distinguish_initiator_from_master_direction(control, name, direction):
    detail = parse_dnp3(_frame(control | direction))
    assert detail["valid"] is True
    assert detail["complete"] is True
    assert f"({name})" in detail["summary"]
    assert detail["purpose"] == ("主站→从站" if direction else "从站→主站")


@pytest.mark.parametrize("control", [0x0E, 0x41])
def test_reserved_link_functions_are_not_mislabeled_as_supported(control):
    detail = parse_dnp3(_frame(control))
    assert detail["valid"] is False
    assert "未知链路功能码" in detail["summary"]


@pytest.mark.parametrize("protocol,direction", [(ProtocolType.Dnp3Client, "TX"), (ProtocolType.Dnp3Server, "RX")])
def test_link_summary_is_shown_in_both_message_list_and_details(protocol, direction):
    handler = SimpleNamespace(
        get_captured_messages=lambda _limit: [
            {
                "sequence_id": 1,
                "direction": direction,
                "data": LINK_STATUS_REQUEST.hex(),
            }
        ]
    )
    formatter = MessageFormatter(SimpleNamespace(protocol_type=protocol, protocol_handler=handler))
    message = formatter.get_messages()[0]
    detail = formatter.get_message_detail(1)
    assert message["description"] == "请求链路状态 (REQUEST_LINK_STATUS)"
    assert detail["summary"] == message["description"]
    assert detail["valid"] is True


@pytest.mark.parametrize("control", [0xC3, 0xC4, 0x43, 0x44])
def test_unknown_application_function_does_not_shift_transport_offsets(control):
    detail = parse_dnp3(_frame(control, bytes.fromhex("C7 C5 7F")))
    assert detail["application_function_code"] == 0x7F
    assert detail["application_sequence"] == 5
    fields = {field["key"]: field for field in detail["fields"]}
    assert fields["transport_control"]["offset"] == 10
    assert fields["app_control"]["offset"] == 11
    assert fields["function_code"]["offset"] == 12


@pytest.mark.parametrize("app_control", [0x80, 0x00, 0x40])
def test_application_fragment_flags_do_not_hide_transport_header(app_control):
    detail = parse_dnp3(_frame(0x44, bytes([0xC0, app_control, 0x81, 0, 0])))
    assert detail["application_function_code"] == 0x81
    assert detail["summary"] == "响应：成功"


def test_real_transport_segments_are_not_misparsed_as_application_headers():
    # Use the production segmenter, and data that resembles a READ header in later segments.
    fragment = bytes.fromhex("C0 81 00 00") + bytes.fromhex("C0 01 3C 01 06") * 120
    segments = Segmenter().segment(fragment)
    correlator = FragmentCorrelator("rx")
    metadata = []
    for index, segment in enumerate(segments):
        raw = _frame(0x44, segment)
        detail = parse_dnp3(raw)
        metadata.append(correlator.metadata(raw))
        kind = "首分段" if index == 0 else ("末分段" if index == len(segments) - 1 else "中间分段")
        assert detail["summary"] == f"DNP3传输层{kind} SEQ={index}"
        assert detail["valid"] is True
        assert detail["complete"] is False
        assert not detail["objects"]
        assert "application_function_code" not in detail
    assert len({item["fragment_correlation_id"] for item in metadata}) == 1
    assert metadata[0]["transport_first"] is True
    assert metadata[0]["transport_final"] is False
    assert metadata[-1]["transport_first"] is False
    assert metadata[-1]["transport_final"] is True


@pytest.mark.parametrize("payload", [b"", b"\xc0", b"\xc0\xc0", b"\xc0\xc0\x81", b"\xc0\xc0\x81\x00"])
def test_missing_transport_or_application_headers_are_reported_as_incomplete(payload):
    detail = parse_dnp3(_frame(0xC4, payload))
    assert detail["valid"] is False
    assert detail["complete"] is False
    assert detail["summary"] != "无法识别该报文"
    assert detail["errors"]


def test_bad_crc_and_extra_bytes_are_not_reported_as_valid():
    detail = parse_dnp3(LINK_STATUS_REQUEST[:-1] + b"\x00")
    crc = next(item for item in detail["validation"] if item["name"] == "链路头CRC")
    assert detail["valid"] is False
    assert crc["passed"] is False
    assert "错误" in crc["detail"]
    assert parse_dnp3(LINK_STATUS_REQUEST + b"\x00")["valid"] is False


def test_response_iin_errors_are_not_described_as_success():
    detail = parse_dnp3(_frame(0x44, bytes.fromhex("C0 C0 81 00 05")))
    assert detail["valid"] is True
    assert "成功" not in detail["summary"]
    assert "功能码不支持" in detail["summary"]
    assert "参数错误" in detail["summary"]


def test_crc_fallback_validates_the_captured_link_header(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "pydnp3_pure.link.crc", None)
    assert _crc16_dnp3(LINK_STATUS_REQUEST[:8]) == 0x8EDE
    assert _crc16_dnp3(b"123456789") == 0xEA82
    assert parse_dnp3(LINK_STATUS_REQUEST)["valid"] is True
