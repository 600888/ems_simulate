"""Wire-format and upgrade checks for descriptive Modbus decode codes."""

import math

import pytest
from sqlalchemy import create_engine, text

from src.data.controller.db_controller import DbController
from src.enums.modbus_register import LEGACY_CODES, Decode, DecodeCode
from src.web.api.schemas.point import PointCreateRequest


@pytest.mark.parametrize("item", list(DecodeCode))
def test_all_codes_round_trip(item):
    info = item.value
    value = 12.5 if info.is_float else -12 if info.is_signed else 12
    registers = Decode.encode_registers(info.code, value)
    assert len(registers) == info.register_cnt
    result = Decode.decode_registers(info.code, registers)
    assert math.isclose(result, value)


@pytest.mark.parametrize(
    ("code", "value", "expected"),
    [
        ("UINT16_BA", 0x1234, [0x3412]),
        ("UINT32_ABCD", 0x12345678, [0x1234, 0x5678]),
        ("UINT32_BADC", 0x12345678, [0x3412, 0x7856]),
        ("UINT32_CDAB", 0x12345678, [0x5678, 0x1234]),
        ("UINT32_DCBA", 0x12345678, [0x7856, 0x3412]),
        ("UINT64_GHEFCDAB", 0x0102030405060708, [0x0708, 0x0506, 0x0304, 0x0102]),
        ("DOUBLE_ABCDEFGH", 1.0, [0x3FF0, 0, 0, 0]),
        ("DOUBLE_BADCFEHG", 1.0, [0xF03F, 0, 0, 0]),
        ("DOUBLE_GHEFCDAB", 1.0, [0, 0, 0, 0x3FF0]),
        ("DOUBLE_HGFEDCBA", 1.0, [0, 0, 0, 0xF03F]),
    ],
)
def test_wire_byte_orders(code, value, expected):
    assert Decode.encode_registers(code, value) == expected
    assert Decode.decode_registers(code, expected) == value


def test_all_legacy_codes_have_valid_migration_targets():
    assert len(LEGACY_CODES) == 27
    for old, new in LEGACY_CODES.items():
        assert Decode.normalize(old) == new
        assert Decode.get_info(old) is Decode.get_info(new)
    with pytest.raises(ValueError, match="未知解析码"):
        Decode.get_info("0xFF")


def test_api_normalizes_legacy_input_and_rejects_unknown_code():
    payload = {
        "device_name": "device",
        "frame_type": 0,
        "code": "P1",
        "name": "Point",
        "reg_addr": "0",
        "decode_code": "0xE2",
    }
    assert PointCreateRequest(**payload).decode_code == "DOUBLE_GHEFCDAB"
    with pytest.raises(ValueError, match="未知解析码"):
        PointCreateRequest(**{**payload, "decode_code": "0xFF"})


def test_sqlite_migration_converts_old_rows_and_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'points.db'}")
    with engine.begin() as conn:
        for table in ("point_yc", "point_yx", "point_yk", "point_yt"):
            conn.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, decode_code VARCHAR(10))"))
            conn.execute(text(f"INSERT INTO {table} (id, decode_code) VALUES (1, '0xE2')"))
    controller = DbController()
    controller._db_type = "sqlite"
    controller.db_config = type("Config", (), {"engine": engine})()
    controller._migrate_decode_codes()
    controller._migrate_decode_codes()
    with engine.connect() as conn:
        for table in ("point_yc", "point_yx", "point_yk", "point_yt"):
            assert conn.scalar(text(f"SELECT decode_code FROM {table}")) == "DOUBLE_GHEFCDAB"
    engine.dispose()
