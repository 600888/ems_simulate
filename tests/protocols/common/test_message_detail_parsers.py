from types import SimpleNamespace

from src.device.core.message.message_formatter import MessageFormatter
from src.device.core.message.parsers import parse_dlt645, parse_iec104, parse_modbus
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

    detail = MessageFormatter(Device()).get_message_detail(2)

    assert detail is not None
    assert detail["correlation"]["request_sequence_id"] == 1
    assert [item["address"] for item in detail["objects"]] == [100, 101]
    assert detail["objects"][0]["point"]["name"] == "母线电压"
    assert detail["objects"][0]["decoded_value"] == 100
    assert detail["objects"][0]["engineering_value"] == 11.0


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
