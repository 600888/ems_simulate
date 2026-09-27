"""Modbus register types and byte-order-aware codecs.

The suffix is the order of bytes on the wire, relative to the usual big-endian
representation of the value. Legacy hexadecimal codes are accepted at input
boundaries, but all newly persisted codes use the descriptive names below.
"""

from dataclasses import dataclass
from enum import Enum
import struct


@dataclass(frozen=True)
class DecodeInfo:
    code: str
    name: str
    description: str
    register_cnt: int
    is_signed: bool
    is_float: bool
    pack_format: str
    order: str
    bit_width: int

    @property
    def is_big_endian(self) -> bool:
        return self.order == "ABCDEFGH" or self.order == "ABCD" or self.order == "AB"

    @property
    def word_swap(self) -> bool:
        return self.order in {"CDAB", "GHEFCDAB"}

    @property
    def endian(self) -> str:
        return ">" if self.is_big_endian else "<"

    @property
    def decode_type(self) -> "DecodeType":
        if self.is_float:
            return DecodeType.Float
        if self.bit_width > 16:
            return DecodeType.SignedLong if self.is_signed else DecodeType.UnsignedLong
        return DecodeType.SignedInt if self.is_signed else DecodeType.UnsignedInt


class DecodeType(Enum):
    SignedInt = 1
    UnsignedInt = 2
    SignedLong = 3
    UnsignedLong = 4
    Float = 5


def _info(name: str) -> DecodeInfo:
    kind, order = name.split("_", 1)
    width = 64 if kind == "DOUBLE" else int(kind.removeprefix("UINT").removeprefix("INT").removeprefix("FLOAT"))
    is_float = kind in {"DOUBLE", "FLOAT32"}
    is_signed = kind.startswith("INT")
    fmt = (
        ("d" if width == 64 else "f")
        if is_float
        else {
            (8, False): "B",
            (8, True): "b",
            (16, False): "H",
            (16, True): "h",
            (32, False): "I",
            (32, True): "i",
            (64, False): "Q",
            (64, True): "q",
        }[(width, is_signed)]
    )
    value_type = "浮点数" if is_float else "有符号整数" if is_signed else "无符号整数"
    return DecodeInfo(
        name,
        name,
        f"{width}位{value_type} ({order})",
        max(1, width // 16),
        is_signed,
        is_float,
        ">" + fmt,
        order,
        width,
    )


class DecodeCode(Enum):
    UINT8_AB = _info("UINT8_AB")
    INT8_AB = _info("INT8_AB")
    UINT8_BA = _info("UINT8_BA")
    INT8_BA = _info("INT8_BA")
    UINT16_AB = _info("UINT16_AB")
    INT16_AB = _info("INT16_AB")
    UINT16_BA = _info("UINT16_BA")
    INT16_BA = _info("INT16_BA")
    UINT32_ABCD = _info("UINT32_ABCD")
    INT32_ABCD = _info("INT32_ABCD")
    FLOAT32_ABCD = _info("FLOAT32_ABCD")
    UINT32_BADC = _info("UINT32_BADC")
    INT32_BADC = _info("INT32_BADC")
    FLOAT32_BADC = _info("FLOAT32_BADC")
    UINT32_CDAB = _info("UINT32_CDAB")
    INT32_CDAB = _info("INT32_CDAB")
    FLOAT32_CDAB = _info("FLOAT32_CDAB")
    UINT32_DCBA = _info("UINT32_DCBA")
    INT32_DCBA = _info("INT32_DCBA")
    FLOAT32_DCBA = _info("FLOAT32_DCBA")
    UINT64_ABCDEFGH = _info("UINT64_ABCDEFGH")
    INT64_ABCDEFGH = _info("INT64_ABCDEFGH")
    UINT64_GHEFCDAB = _info("UINT64_GHEFCDAB")
    INT64_GHEFCDAB = _info("INT64_GHEFCDAB")
    DOUBLE_ABCDEFGH = _info("DOUBLE_ABCDEFGH")
    DOUBLE_BADCFEHG = _info("DOUBLE_BADCFEHG")
    DOUBLE_GHEFCDAB = _info("DOUBLE_GHEFCDAB")
    DOUBLE_HGFEDCBA = _info("DOUBLE_HGFEDCBA")


# These aliases follow the actual Modbus client/server register behavior before
# this refactor. Several old descriptions claimed a different byte order.
LEGACY_CODES: dict[str, str] = {
    "0x10": "UINT8_AB",
    "0x11": "INT8_AB",
    "0x20": "UINT16_AB",
    "0x21": "INT16_AB",
    "0x22": "UINT16_AB",
    "0xB0": "UINT16_AB",
    "0xB1": "INT16_AB",
    "0xC0": "UINT16_BA",
    "0xC1": "INT16_BA",
    "0x40": "UINT32_ABCD",
    "0x41": "INT32_ABCD",
    "0x42": "FLOAT32_ABCD",
    "0x43": "UINT32_DCBA",
    "0x44": "INT32_DCBA",
    "0x45": "FLOAT32_DCBA",
    "0xD0": "UINT32_CDAB",
    "0xD1": "INT32_CDAB",
    "0xD2": "FLOAT32_CDAB",
    "0xD3": "FLOAT32_CDAB",
    "0xD4": "UINT32_CDAB",
    "0xD5": "INT32_CDAB",
    "0x60": "UINT64_ABCDEFGH",
    "0x61": "INT64_ABCDEFGH",
    "0x62": "DOUBLE_ABCDEFGH",
    "0xE0": "UINT64_GHEFCDAB",
    "0xE1": "INT64_GHEFCDAB",
    "0xE2": "DOUBLE_GHEFCDAB",
}
_LEGACY_UPPER = {old.upper(): new for old, new in LEGACY_CODES.items()}


class Decode:
    _CODE_MAP: dict[str, DecodeInfo] = {item.value.code: item.value for item in DecodeCode}
    DEFAULT = DecodeCode.INT32_ABCD.value

    @classmethod
    def normalize(cls, decode: str) -> str:
        if not isinstance(decode, str):
            raise ValueError(f"未知解析码: {decode!r}")
        code = _LEGACY_UPPER.get(decode.upper(), decode.upper())
        if code not in cls._CODE_MAP:
            raise ValueError(f"未知解析码: {decode!r}")
        return code

    @classmethod
    def get_info(cls, decode: str) -> DecodeInfo:
        return cls._CODE_MAP[cls.normalize(decode)]

    @classmethod
    def get_all_codes(cls) -> list[dict]:
        return [
            {
                "code": info.code,
                "name": info.name,
                "description": info.description,
                "register_cnt": info.register_cnt,
                "order": info.order,
                "bit_width": info.bit_width,
            }
            for info in cls._CODE_MAP.values()
        ]

    @classmethod
    def get_decode_register_cnt(cls, decode: str) -> int:
        return cls.get_info(decode).register_cnt

    @classmethod
    def get_endian(cls, decode: str) -> str:
        return cls.get_info(decode).endian

    @classmethod
    def is_decode_signed(cls, decode: str) -> bool:
        return cls.get_info(decode).is_signed

    @classmethod
    def get_decode_type(cls, decode: str) -> DecodeType:
        return cls.get_info(decode).decode_type

    @classmethod
    def get_byteorder(cls, decode: str) -> str:
        return cls.get_info(decode).pack_format

    @classmethod
    def get_limits_by_code(cls, decode: str, mul_coe: float = 1.0, add_coe: float = 0.0) -> tuple[float, float]:
        info = cls.get_info(decode)
        if info.is_float:
            raw_min, raw_max = -999999999.0, 999999999.0
        elif info.is_signed:
            raw_min, raw_max = -(1 << (info.bit_width - 1)), (1 << (info.bit_width - 1)) - 1
        else:
            raw_min, raw_max = 0, (1 << info.bit_width) - 1
        low = raw_min * mul_coe + add_coe
        high = raw_max * mul_coe + add_coe
        return max(low, high), min(low, high)

    @classmethod
    def encode_registers(cls, decode: str, value: int | float) -> list[int]:
        info = cls.get_info(decode)
        raw = struct.pack(info.pack_format, float(value) if info.is_float else int(value))
        if info.bit_width == 8:
            wire = b"\x00" + raw if info.order == "AB" else raw + b"\x00"
        else:
            canonical = "ABCDEFGH"[: len(raw)]
            wire = bytes(raw[canonical.index(letter)] for letter in info.order)
        return [int.from_bytes(wire[i : i + 2], "big") for i in range(0, len(wire), 2)]

    @classmethod
    def decode_registers(cls, decode: str, registers: list[int]) -> int | float:
        info = cls.get_info(decode)
        if len(registers) != info.register_cnt:
            raise ValueError(f"{info.code} 需要 {info.register_cnt} 个寄存器")
        wire = b"".join(int(reg).to_bytes(2, "big") for reg in registers)
        if info.bit_width == 8:
            raw = wire[1:2] if info.order == "AB" else wire[:1]
        else:
            canonical = "ABCDEFGH"[: len(wire)]
            raw = bytes(wire[info.order.index(letter)] for letter in canonical)
        return struct.unpack(info.pack_format, raw)[0]

    @classmethod
    def pack_value(cls, byteorder: str, value) -> bytes:
        """Compatibility helper for external struct-format callers."""
        fmt = byteorder.rstrip("_")
        packed = struct.pack(fmt, float(value) if fmt[-1] in "fd" else int(value))
        if byteorder.endswith("_"):
            words = [packed[i : i + 2] for i in range(0, len(packed), 2)]
            return b"".join(words[i ^ 1] for i in range(len(words))) if len(words) % 2 == 0 else packed
        return packed

    @classmethod
    def unpack_value(cls, byteorder: str, buffer: bytes):
        fmt = byteorder.rstrip("_")
        if byteorder.endswith("_"):
            words = [buffer[i : i + 2] for i in range(0, len(buffer), 2)]
            if len(words) % 2 == 0:
                buffer = b"".join(words[i ^ 1] for i in range(len(words)))
        return struct.unpack(fmt, buffer)[0]


class ByteOrder(Enum):
    """Legacy struct formats retained for callers outside the code registry."""

    BigEndFloat = ">f"
    LittleEndFloat = "<f"
    WordSwappedFloat = "=f"
    LittleEndWordSwappedFloat = "<f_"
    BigEndSignedInt = ">i"
    LittleEndSignedInt = "<i"
    BigEndUnsignedInt = ">I"
    LittleEndUnsignedInt = "<I"
    BigEndSignedShort = ">h"
    LittleEndSignedShort = "<h"
    BigEndUnsignedShort = ">H"
    LittleEndUnsignedShort = "<H"
    BigEndWordSwappedSignedInt = "=i"
    BigEndWordSwappedUnsignedInt = "=I"
    BigEndWordSwappedSignedShort = "=h"
    BigEndWordSwappedUnsignedShort = "=H"
    LittleEndWordSwappedSignedInt = "<i_"
    LittleEndWordSwappedUnsignedInt = "<I_"
    LittleEndWordSwappedSignedShort = "<h_"
    LittleEndWordSwappedUnsignedShort = "<H_"
