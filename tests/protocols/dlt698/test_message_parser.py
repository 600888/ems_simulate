"""Wire vectors, corrupted captures and formatter integration for DL/T 698.45."""

import json
import random
from types import SimpleNamespace

from dlt698 import model as m
from dlt698 import protocol as p
from dlt698.codec import Frame, encode_apdu, encode_frame, encode_security
from dlt698.protocol.link import ServerAddress
import pytest

from src.device.core.message.message_formatter import MessageFormatter
from src.device.core.message.parsers import parse_dlt698
from src.enums.modbus_def import ProtocolType
from src.proto.dlt698.runtime import Dlt698Runtime
from src.proto.dlt698.schema import Dlt698Config


def oad(oi=0x2000, index=0):
    return m.Oad(oi=oi, attribute=2, index=index)


def attribute(value=None):
    return p.AttributeResult(attribute=oad(), result=value if value is not None else m.Data.uint16(2200))


def frame(apdu=None, *, payload=None, control=0x43, address=b"\x01\x02\x03\x04\x05\x06"):
    return encode_frame(
        Frame(
            control=control,
            server=ServerAddress(bytes=address),
            client=0x10,
            payload=payload if payload is not None else encode_apdu(apdu),
        )
    )


def field(detail, key):
    return next(item for item in detail["fields"] if item["key"] == key)


def assert_spans(detail, raw):
    for item in detail["fields"] + detail["objects"]:
        offset, length = item["offset"], item["length"]
        assert 0 <= offset <= offset + length <= len(raw)
        expected = item.get("raw_hex", item.get("raw_value"))
        assert bytes.fromhex(expected) == raw[offset : offset + length]
    json.dumps(detail, ensure_ascii=False, allow_nan=False)


def test_known_get_request_vector():
    # Fixed wire vector, independent of the frame builder used by the other tests.
    raw = bytes.fromhex("68 17 00 43 05 01 02 03 04 05 06 10 3D FC 05 01 01 20 00 02 00 00 CE BA 16")
    detail = parse_dlt698(raw, role="Request")
    assert detail["valid"] and detail["complete"]
    assert detail["role"] == "request"
    assert "GET" in detail["summary"] and "20000200" in detail["summary"]
    assert field(detail, "server_address")["value"] == "060504030201"
    assert field(detail, "piid")["value"] == 1
    assert field(detail, "oad")["offset"] == 17
    assert all(item["passed"] for item in detail["validation"])
    assert_spans(detail, raw)


@pytest.mark.parametrize(
    "server_address,wire_address",
    [
        ("12", "12"),
        ("1234567890ab", "ab9078563412"),
        ("0123456789abcdef1020304050607080", "8070605040302010efcdab8967452301"),
        ("010147804870", "704880470101"),
    ],
)
@pytest.mark.parametrize("role", ["client", "server"])
def test_configured_server_address_converts_to_wire_and_back_to_display(server_address, wire_address, role):
    config = Dlt698Config(role=role, server_address=server_address)
    options = Dlt698Runtime(config, {}).options()
    assert options.server.bytes == bytes.fromhex(wire_address)
    raw = encode_frame(
        Frame(
            server=options.server, client=options.client_address, payload=encode_apdu(p.GetRequest(attributes=[oad()]))
        )
    )
    captures = [{"sequence_id": 1, "direction": "TX" if role == "client" else "RX", "data": raw.hex()}]
    formatter = MessageFormatter(
        SimpleNamespace(
            protocol_type=ProtocolType.Dlt698Client if role == "client" else ProtocolType.Dlt698Server,
            protocol_handler=SimpleNamespace(get_captured_messages=lambda _limit: captures),
        )
    )
    detail = formatter.get_message_detail(1)
    address_field = field(detail, "server_address")
    assert detail["valid"] and detail["complete"]
    assert address_field["value"] == config.server_address
    assert address_field["display_value"] == config.server_address
    assert bytes.fromhex(address_field["raw_hex"]) == bytes.fromhex(wire_address)
    assert f"服务器地址:{config.server_address}" in detail["summary"]
    assert f"服务器地址:{config.server_address}" in formatter.get_messages()[0]["description"]
    assert_spans(detail, raw)


@pytest.mark.parametrize("control", [0x83, 0x8B])
def test_nested_data_and_scrambling_preserve_transmitted_bytes(control):
    value = m.Data.structure([m.Data.uint64(2**64 - 1), m.Data.array([m.Data.int32(-12), m.Data.boolean(True)])])
    raw = b"\xfe" * 4 + frame(p.GetResponse(attributes=[attribute(value)], piid_acd=0x81), control=control)
    detail = parse_dlt698(raw, role="Response")
    assert detail["valid"] and detail["complete"]
    assert detail["objects"][0]["value"]["value"][0]["value"] == str(2**64 - 1)
    assert field(detail, "data")["value"]["type"] == "structure"
    assert field(detail, "piid")["offset"] == 20
    assert_spans(detail, raw)


@pytest.mark.parametrize(
    "apdu",
    [
        p.GetRequest(attributes=[oad(), oad(index=1)], list=True),
        p.GetResponse(attributes=[attribute(), attribute(4)], list=True),
        p.SetRequest(attributes=[p.SetAttribute(attribute=oad(), value=m.Data.uint16(2300))]),
        p.SetResponse(attributes=[p.SetResult(attribute=oad(), dar=3)]),
        p.ActionRequest(methods=[p.ActionMethod(method=m.Omd(oi=0xF001, method=1), parameter=m.Data.null())]),
        p.ActionResponse(methods=[p.ActionResult(method=m.Omd(oi=0xF001, method=1), dar=0, data=m.Data.uint8(1))]),
        p.ActionResponse(methods=[p.ActionResult(method=m.Omd(oi=0xF001, method=1), dar=3)]),
        p.ReportNotification(payload=[attribute()]),
        p.ReportResponse(attributes=[oad()]),
        p.GetMd5Request(attribute=oad()),
        p.GetMd5Response(attribute=oad(), result=list(range(16))),
        p.GetMd5Response(attribute=oad(), result=4),
        p.GetNextRequest(block=2),
        p.GetNextResponse(block=2, last=True, result=[attribute()]),
        p.GetNextResponse(block=2, last=True, result=4),
        p.SetThenGetRequest(
            items=[p.SetThenGet(set=p.SetAttribute(attribute=oad(), value=m.Data.uint16(1)), read=oad())]
        ),
        p.SetThenGetResponse(items=[p.SetThenGetResult(set=p.SetResult(attribute=oad(), dar=0), read=attribute())]),
        p.ActionThenGetRequest(
            items=[
                p.ActionThenGet(
                    action=p.ActionMethod(method=m.Omd(oi=0xF001, method=1), parameter=m.Data.null()), read=oad()
                )
            ]
        ),
        p.ActionThenGetResponse(
            items=[
                p.ActionThenGetResult(action=p.ActionResult(method=m.Omd(oi=0xF001, method=1), dar=0), read=attribute())
            ]
        ),
    ],
)
def test_application_services(apdu):
    raw = frame(apdu)
    detail = parse_dlt698(raw, role="Request")
    assert detail["valid"] and detail["complete"], detail
    assert detail["apdu"]["type"] == type(apdu).__name__
    assert not detail["warnings"]
    assert_spans(detail, raw)


def test_dar_is_business_failure_without_invalidating_frame():
    detail = parse_dlt698(frame(p.GetResponse(attributes=[attribute(4)])), role="Response")
    assert detail["valid"]
    assert "对象未定义" in detail["summary"]
    assert detail["objects"][0]["quality"] == {"dar": 4, "success": False}


def test_action_failure_with_returned_data_keeps_error_summary():
    apdu = p.ActionResponse(methods=[p.ActionResult(method=m.Omd(oi=0xF001, method=1), dar=3, data=m.Data.uint8(1))])
    detail = parse_dlt698(frame(apdu), role="Response")
    assert detail["valid"] and "拒绝读写" in detail["summary"]
    assert detail["objects"][0]["value"]["value"] == 1


def test_record_request_retains_selector_and_columns():
    apdu = p.GetRecordRequest(records=[p.GetRecord(attribute=oad(0x5004), columns=[oad()], rows=m.SelectAll())])
    raw = frame(apdu)
    detail = parse_dlt698(raw, role="Request")
    assert detail["valid"] and detail["complete"]
    assert detail["objects"][0]["address"] == "50040200"
    assert field(detail, "record_query")["value"]["columns"][0]["oi"] == 0x2000
    assert_spans(detail, raw)


@pytest.mark.parametrize("dar", [False, True])
def test_records_follow_reports_and_time_tag(dar):
    record = p.RecordResult(attribute=oad(0x5004), columns=[oad()], result=4 if dar else [[m.Data.uint16(12)]])
    apdu = p.GetRecordResponse(
        records=[record],
        follow_report=[attribute()],
        time_tag=p.TimeTag(sent_at=m.DateTimeS(value=[7, 234, 10, 20, 12, 0, 0]), allowed_delay=m.Ti(interval=10)),
    )
    raw = frame(apdu)
    detail = parse_dlt698(raw, role="Response")
    assert detail["valid"] and detail["complete"], detail
    assert detail["objects"][0]["address"] == "50040200"
    assert len(detail["objects"]) == 2
    assert field(detail, "time_tag")["length"] == 10
    assert_spans(detail, raw)


@pytest.mark.parametrize("as_report", [True, False])
def test_record_notifications_and_record_follow_report(as_report):
    record = p.RecordResult(attribute=oad(0x5004), columns=[oad()], result=[])
    apdu = (
        p.ReportNotification(payload=[record])
        if as_report
        else p.GetResponse(attributes=[attribute()], follow_report=[record])
    )
    raw = frame(apdu)
    detail = parse_dlt698(raw, role="Response")
    assert detail["valid"] and detail["complete"], detail
    assert any(item["name"] == "记录" for item in detail["objects"])
    assert_spans(detail, raw)


@pytest.mark.parametrize(
    "apdu",
    [
        p.LinkRequest(),
        p.LinkResponse(),
        p.ConnectRequest(),
        p.ConnectResponse(),
        p.ReleaseRequest(),
        p.ReleaseResponse(),
        p.ErrorResponse(type=1),
    ],
)
def test_connection_and_error_services_remain_json_safe(apdu):
    raw = frame(apdu)
    detail = parse_dlt698(raw, role="Response")
    assert detail["valid"] and detail["complete"], detail
    assert detail["apdu"]["type"] == type(apdu).__name__
    assert_spans(detail, raw)


@pytest.mark.parametrize("position,check", [(7, "HCS"), (-2, "FCS"), (-1, "结束符")])
def test_corruption_is_reported_without_losing_raw_or_objects(position, check):
    raw = bytearray(frame(p.GetRequest(attributes=[oad()]), address=b"\x01"))
    raw[position] ^= 1
    raw = bytes(raw)
    detail = parse_dlt698(raw, role="Request")
    assert not detail["valid"]
    assert not next(item for item in detail["validation"] if item["name"] == check)["passed"]
    assert detail["objects"][0]["address"] == "20000200"
    assert_spans(detail, raw)


def test_truncated_frames_never_raise_and_preserve_all_bytes():
    raw = frame(p.GetResponse(attributes=[attribute()]))
    for end in range(len(raw)):
        detail = parse_dlt698(raw[:end], role="Response")
        assert not detail["valid"] and not detail["complete"]
        assert detail["raw_length"] == end
        assert_spans(detail, raw[:end])


def test_extra_frames_are_not_silently_ignored():
    raw = frame(p.GetRequest(attributes=[oad()])) * 2
    detail = parse_dlt698(raw, role="Request")
    assert not detail["valid"] and not detail["complete"]
    assert detail["warnings"] and field(detail, "trailing")
    assert_spans(detail, raw)


def test_unknown_service_and_malformed_known_service():
    unknown = parse_dlt698(frame(payload=b"\xff\x01\x02"), role="Request")
    malformed = parse_dlt698(frame(payload=b"\x05\x01"), role="Request")
    assert unknown["valid"] and not unknown["complete"] and unknown["warnings"]
    assert not malformed["valid"] and malformed["errors"]


def test_fragments_do_not_decode_incomplete_apdu():
    raw = frame(payload=b"\x00\x00\x05\x01", control=0x63)
    detail = parse_dlt698(raw, role="Request")
    assert detail["valid"] and not detail["complete"]
    assert not detail["objects"] and "分帧" in detail["summary"]


def test_security_envelope_remains_visible_without_claiming_decryption():
    raw = frame(
        payload=encode_security(
            p.SecurityRequest(application=b"secret", encrypted=True, verification=m.Rn(value=b"12345678"))
        )
    )
    detail = parse_dlt698(raw, role="Request")
    assert detail["valid"] and not detail["complete"]
    assert field(detail, "security") and detail["warnings"]
    assert_spans(detail, raw)


def test_random_payloads_do_not_break_capture_inspection():
    rng = random.Random(698)
    for _ in range(200):
        raw = frame(payload=rng.randbytes(rng.randrange(0, 80)))
        assert_spans(parse_dlt698(raw, role="Request"), raw)


@pytest.mark.parametrize(
    "protocol_type,directions",
    [
        (ProtocolType.Dlt698Client, ("TX", "RX")),
        (ProtocolType.Dlt698Server, ("RX", "TX")),
    ],
)
def test_formatter_list_detail_directions_and_point_semantics(protocol_type, directions):
    captures = [
        {"sequence_id": index, "direction": direction, "data": frame(apdu).hex(), "timestamp": float(index)}
        for index, direction, apdu in [
            (1, directions[0], p.GetRequest(attributes=[oad()])),
            (2, directions[1], p.GetResponse(attributes=[attribute()])),
        ]
    ]
    point = SimpleNamespace(
        code="voltage",
        name="A相电压",
        definition={
            "oad": "20000200",
            "scaler": -1,
            "unit": "V",
            "data_type": "UInt16",
        },
    )
    device = SimpleNamespace(
        protocol_type=protocol_type,
        protocol_handler=SimpleNamespace(get_captured_messages=lambda _limit: captures),
        point_manager=SimpleNamespace(get_all_points=lambda: [point]),
    )
    formatter = MessageFormatter(device)
    messages = formatter.get_messages()
    assert [item["msg_type"] for item in messages] == ["Request", "Response"]
    assert all("GET" in item["description"] for item in messages)
    detail = formatter.get_message_detail(2)
    assert detail["sequence_id"] == 2 and detail["direction"] == directions[1]
    assert detail["objects"][0]["name"] == "A相电压"
    assert detail["objects"][0]["unit"] == "V"
    assert detail["objects"][0]["engineering_value"] == "220.0"
    assert formatter.get_message_detail(99) is None
