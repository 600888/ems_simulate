from types import SimpleNamespace

from src.device.core.message.message_formatter import MessageFormatter
from src.device.core.message.parsers import parse_dlt645, parse_dnp3, parse_iec104, parse_modbus
from src.enums.modbus_def import ProtocolType


def test_modbus_tcp_detail_keeps_raw_frame_and_offsets():
    raw = bytes.fromhex("000100000006010300000009")
    detail = parse_modbus(raw, tcp=True, role="Request")

    assert detail["raw_hex"] == "00 01 00 00 00 06 01 03 00 00 00 09"
    assert detail["raw_length"] == len(raw)
    assert detail["valid"] is True
    assert next(field for field in detail["fields"] if field["key"] == "function_code")["offset"] == 7


def test_modbus_rtu_detail_reports_crc_failure_without_hiding_raw_frame():
    raw = bytes.fromhex("0103000000010000")
    detail = parse_modbus(raw, tcp=False, role="Request")

    assert detail["raw_hex"]
    assert detail["valid"] is False
    assert next(item for item in detail["validation"] if item["name"] == "CRC16")["passed"] is False


def test_dlt645_detail_exposes_encoded_and_decoded_data():
    raw = bytes.fromhex("6812345678901268110433333435D316")
    detail = parse_dlt645(raw, role="Request")

    assert detail["raw_hex"] == "68 12 34 56 78 90 12 68 11 04 33 33 34 35 D3 16"
    assert next(field for field in detail["fields"] if field["key"] == "data_encoded")["raw_hex"] == "33 33 34 35"
    assert next(field for field in detail["fields"] if field["key"] == "data_decoded")["display_value"] == "00 00 01 02"


def test_iec104_u_frame_keeps_complete_raw_frame():
    raw = bytes.fromhex("680407000000")
    detail = parse_iec104(raw, role="Request")

    assert detail["raw_hex"] == "68 04 07 00 00 00"
    assert detail["frame_kind"] == "U格式帧"
    assert "STARTDT_ACT" in detail["summary"]


def _dnp3_frame(user_data: bytes) -> bytes:
    from pydnp3_pure.link.frame import LinkFrame

    return LinkFrame.create(
        destination=1,
        source=1024,
        primary=True,
        function=3,
        user_data=user_data,
    ).serialize()


def test_dnp3_detail_parses_transport_and_application_headers():
    # 传输控制 C0 + 应用控制 C0 + READ + G60V1 全部点。
    raw = _dnp3_frame(bytes.fromhex("C0 C0 01 3C 01 06"))

    detail = parse_dnp3(raw, role="Request")

    assert detail["valid"] is True
    assert detail["summary"] == "读 (Read)，G60V1，全部点"
    assert next(field for field in detail["fields"] if field["key"] == "transport_control")["offset"] == 10
    assert next(field for field in detail["fields"] if field["key"] == "function_code")["offset"] == 12
    assert detail["objects"][0]["name"] == "G60V1 类数据"
    assert detail["objects"][0]["address"] is None


def test_dnp3_detail_validates_all_16_byte_data_blocks():
    # 超过 16 字节，覆盖 DNP3 每 16 数据字节追加一次 CRC 的布局。
    from pydnp3_pure.app.constants import Qualifier
    from pydnp3_pure.app.fragment import ObjectData, build_response
    from pydnp3_pure.app.header import IIN
    from pydnp3_pure.app.object_header import ObjectHeader
    from pydnp3_pure.objects.types import AnalogPoint

    header = ObjectHeader(30, 1, Qualifier.RANGE_16_START_STOP, 3, 6, 4)
    points = [AnalogPoint(index=index, value=index * 10) for index in range(3, 7)]
    app = build_response(0, IIN(), [ObjectData(header, points)])
    raw = _dnp3_frame(b"\xc0" + app)

    detail = parse_dnp3(raw, role="Response")

    assert next(item for item in detail["validation"] if item["name"] == "数据块CRC")["passed"] is True
    assert detail["summary"] == "响应：成功，G30V1，地址 3～6"
    assert [item["address"] for item in detail["objects"]] == [3, 4, 5, 6]
    assert [item["value"] for item in detail["objects"]] == [30, 40, 50, 60]
    assert all(item["quality"]["online"] for item in detail["objects"])


def test_formatter_populates_dnp3_description_and_client_direction():
    raw = _dnp3_frame(bytes.fromhex("C0 C0 01 3C 01 06"))
    handler = SimpleNamespace(
        get_captured_messages=lambda _limit: [
            {
                "sequence_id": 1,
                "direction": "TX",
                "data": raw.hex(),
                "timestamp": 1.0,
                "time": "t1",
                "length": len(raw),
            }
        ]
    )
    device = SimpleNamespace(protocol_handler=handler, protocol_type=ProtocolType.Dnp3Client)

    message = MessageFormatter(device).get_messages()[0]

    assert message["msg_type"] == "Request"
    assert message["description"] == "读 (Read)，G60V1，全部点"


def test_formatter_enriches_dnp3_objects_with_configured_point():
    from pydnp3_pure.app.constants import Qualifier
    from pydnp3_pure.app.fragment import ObjectData, build_response
    from pydnp3_pure.app.header import IIN
    from pydnp3_pure.app.object_header import ObjectHeader
    from pydnp3_pure.objects.types import AnalogPoint

    header = ObjectHeader(30, 1, Qualifier.RANGE_16_START_STOP, 3, 3, 1)
    app = build_response(0, IIN(), [ObjectData(header, [AnalogPoint(index=3, value=220)])])
    raw = _dnp3_frame(b"\xc0" + app)
    handler = SimpleNamespace(
        get_captured_messages=lambda _limit: [
            {
                "sequence_id": 1,
                "direction": "RX",
                "data": raw.hex(),
                "timestamp": 1.0,
                "time": "t1",
                "length": len(raw),
            }
        ]
    )
    point = SimpleNamespace(
        rtu_addr=1,
        func_code=0,
        address=3,
        name="母线电压",
        code="BUS_V",
        frame_type=0,
        decode="0x41",
        iec_type_id=None,
        mul_coe=0.1,
        add_coe=1,
    )
    device = SimpleNamespace(
        protocol_handler=handler,
        protocol_type=ProtocolType.Dnp3Client,
        point_manager=SimpleNamespace(get_all_points=lambda: [point]),
    )

    detail = MessageFormatter(device).get_message_detail(1)

    assert detail is not None
    assert detail["objects"][0]["address"] == 3
    assert detail["objects"][0]["point"]["name"] == "母线电压"
    assert detail["objects"][0]["engineering_value"] == 23.0


def test_dnp3_read_range_expands_concrete_addresses():
    from pydnp3_pure.app.constants import FunctionCode, Qualifier
    from pydnp3_pure.app.fragment import ObjectData, build_request
    from pydnp3_pure.app.object_header import ObjectHeader

    header = ObjectHeader(30, 1, Qualifier.RANGE_16_START_STOP, 10, 12, 3)
    app = build_request(FunctionCode.READ, 0, [ObjectData(header)])

    detail = parse_dnp3(_dnp3_frame(b"\xc0" + app), role="Request")

    assert detail["summary"] == "读 (Read)，G30V1，地址 10～12"
    assert [item["address"] for item in detail["objects"]] == [10, 11, 12]
    assert all(item["value"] == "对象选择" for item in detail["objects"])


def test_dnp3_direct_operate_decodes_index_and_command_value():
    from pydnp3_pure.app.constants import FunctionCode, Qualifier
    from pydnp3_pure.app.fragment import ObjectData, build_request
    from pydnp3_pure.app.object_header import ObjectHeader
    from pydnp3_pure.objects.types import CROB

    header = ObjectHeader(12, 1, Qualifier.INDEX_16, 0, 0, 1)
    command = CROB(control=3, count=1, on_time_ms=100, off_time_ms=200)
    app = build_request(FunctionCode.DIRECT_OPERATE, 0, [ObjectData(header, [(7, command)])])

    detail = parse_dnp3(_dnp3_frame(b"\xc0" + app), role="Request")

    assert detail["summary"] == "直接操作 (Direct Operate)，G12V1，地址 7"
    assert detail["objects"][0]["address"] == 7
    assert detail["objects"][0]["value"] == {
        "control": 3,
        "count": 1,
        "on_time_ms": 100,
        "off_time_ms": 200,
    }
    assert detail["objects"][0]["quality"] == {"status": 0}


def _dlt_frame(control: int, decoded_data: bytes) -> bytes:
    encoded = bytes((byte + 0x33) & 0xFF for byte in decoded_data)
    frame = bytearray.fromhex("6812345678901268")
    frame.extend((control, len(encoded)))
    frame.extend(encoded)
    frame.append(sum(frame) & 0xFF)
    frame.append(0x16)
    return bytes(frame)


def test_dlt645_response_resolves_di_and_bcd_value():
    # DI 02010100 (A相电压), decoded data 0x2201 -> 220.1 for format XXX.X.
    detail = parse_dlt645(_dlt_frame(0x91, bytes.fromhex("000101020122")), role="Response")

    data_object = detail["objects"][0]
    assert data_object["address"] == "0x02010100"
    assert data_object["value"] == "220.1"
    assert data_object["unit"] == "V"
    assert detail["raw_hex"]


def test_iec104_short_float_quality_and_cp56_timestamp():
    # M_ME_TF_1, IOA=1, value=12.5, QDS=IV|NT|BL, 2026-07-13 12:34:12.345.
    asdu = bytes.fromhex("24010300010001000000004841D03930220C0D071A")
    raw = bytes((0x68, len(asdu) + 4, 0, 0, 0, 0)) + asdu
    detail = parse_iec104(raw, role="Response")

    obj = detail["objects"][0]
    assert obj["address"] == 1
    assert obj["value"] == 12.5
    assert obj["quality"]["invalid"] is True
    assert obj["quality"]["not_topical"] is True
    assert obj["quality"]["blocked"] is True
    assert obj["timestamp"] == "2026-07-13 12:34:12.345"
    assert (obj["offset"], obj["length"]) == (12, 15)
    assert detail["raw_hex"]


def test_iec104_single_command_decodes_select_bit_from_same_byte():
    asdu = bytes.fromhex("2D010600010005000081")
    raw = bytes((0x68, len(asdu) + 4, 0, 0, 0, 0)) + asdu
    detail = parse_iec104(raw, role="Request")

    obj = detail["objects"][0]
    assert obj["value"] is True
    assert obj["quality"]["select"] is True
    assert obj["raw_value"] == "81"


def test_modbus_response_context_restores_register_addresses():
    raw = bytes.fromhex("000100000007010304006400C8")
    detail = parse_modbus(
        raw,
        tcp=True,
        role="Response",
        request_context={
            "request_sequence_id": 9,
            "start_address": 100,
            "end_address": 101,
            "quantity": 2,
            "match_method": "transaction_id",
        },
    )

    assert [item["address"] for item in detail["objects"]] == [100, 101]
    assert [(item["offset"], item["length"]) for item in detail["objects"]] == [(9, 2), (11, 2)]
    assert detail["correlation"]["request_sequence_id"] == 9


def test_formatter_correlates_modbus_tcp_response_by_transaction_id():
    class Handler:
        def get_captured_messages(self, _count):
            return [
                {
                    "sequence_id": 1,
                    "direction": "TX",
                    "data": "000100000006010300640002",
                    "hex_string": "00 01 00 00 00 06 01 03 00 64 00 02",
                    "timestamp": 1.0,
                    "time": "t1",
                    "length": 12,
                },
                {
                    "sequence_id": 2,
                    "direction": "RX",
                    "data": "000100000007010304006400c8",
                    "hex_string": "00 01 00 00 00 07 01 03 04 00 64 00 C8",
                    "timestamp": 2.0,
                    "time": "t2",
                    "length": 13,
                },
            ]

    class Device:
        protocol_type = ProtocolType.ModbusTcpClient
        protocol_handler = Handler()
        point_manager = SimpleNamespace(
            get_all_points=lambda: [
                SimpleNamespace(
                    rtu_addr=1,
                    func_code=3,
                    address=100,
                    name="母线电压",
                    code="BUS_V",
                    frame_type=0,
                    decode="0x20",
                    iec_type_id=None,
                    mul_coe=0.1,
                    add_coe=1,
                )
            ]
        )

    formatter = MessageFormatter(Device())
    messages = formatter.get_messages()
    detail = formatter.get_message_detail(2)

    assert [message["slave_id"] for message in messages] == [1, 1]
    assert all(message["protocol_type"] == "ModbusTcpClient" for message in messages)
    assert detail is not None
    assert detail["correlation"]["request_sequence_id"] == 1
    assert [item["address"] for item in detail["objects"]] == [100, 101]
    assert detail["objects"][0]["point"]["name"] == "母线电压"
    assert detail["objects"][0]["decoded_value"] == 100
    assert detail["objects"][0]["engineering_value"] == 11.0


def test_formatter_classifies_iec104_i_frames_by_common_address():
    asdu = bytes.fromhex("2D010600020005000001")
    i_frame = bytes((0x68, len(asdu) + 4, 0, 0, 0, 0)) + asdu
    handler = SimpleNamespace(
        get_captured_messages=lambda _limit: [
            {
                "sequence_id": 1,
                "direction": "RX",
                "data": "680407000000",
                "timestamp": 1.0,
                "time": "t1",
                "length": 6,
            },
            {
                "sequence_id": 2,
                "direction": "RX",
                "data": i_frame.hex(),
                "timestamp": 2.0,
                "time": "t2",
                "length": len(i_frame),
            },
        ]
    )
    device = SimpleNamespace(protocol_handler=handler, protocol_type=ProtocolType.Iec104Server)

    messages = MessageFormatter(device).get_messages()

    assert [message["slave_id"] for message in messages] == [None, 2]
    assert all(message["protocol_type"] == "Iec104Server" for message in messages)


def test_formatter_applies_point_coefficients_to_iec104_raw_value():
    point = SimpleNamespace(
        rtu_addr=1,
        func_code=3,
        address=100,
        name="Voltage",
        code="VOLTAGE",
        frame_type=0,
        decode="0x41",
        iec_type_id="M_ME_NB_1",
        mul_coe=0.1,
        add_coe=5,
    )
    device = SimpleNamespace(
        protocol_type=ProtocolType.Iec104Server,
        protocol_handler=SimpleNamespace(),
        point_manager=SimpleNamespace(get_all_points=lambda: [point]),
    )
    detail = {
        "fields": [{"key": "common_address", "value": 1}],
        "objects": [{"address": 100, "value": 100}],
    }

    MessageFormatter(device)._enrich_with_points(detail, ProtocolType.Iec104Server)

    assert detail["objects"][0]["engineering_value"] == 15


def test_iec104_integrated_total_decodes_bcr_flags():
    # M_IT_NA_1, counter=-2, BCR sequence=3, carry and invalid flags set.
    asdu = bytes.fromhex("0F0103000100010000FEFFFFFFA3")
    raw = bytes((0x68, len(asdu) + 4, 0, 0, 0, 0)) + asdu
    detail = parse_iec104(raw, role="Response")

    obj = detail["objects"][0]
    assert obj["value"] == -2
    assert obj["quality"]["sequence"] == 3
    assert obj["quality"]["carry"] is True
    assert obj["quality"]["invalid"] is True
