"""IEC 60870-5 ASDU codec.

IEC 60870-5-101 and IEC 60870-5-104 use the same application service data
units.  Only their link/transport layers and configurable address widths
differ.  This module deliberately has no serial or TCP dependency so both
protocol implementations can share the application layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import struct
from typing import Any

from src.enums.points.iec104_type import get_iec104_type_by_code, get_iec104_type_info


class ASDUCodecError(ValueError):
    """Raised when an ASDU is malformed or uses an unsupported type."""


@dataclass(slots=True)
class InformationObject:
    io_address: int
    value: Any = None
    quality: int = 0
    timestamp: datetime | None = None
    qualifier: int = 0
    select: bool = False


@dataclass(slots=True)
class ASDU:
    type_id: int
    cause: int
    common_address: int
    objects: list[InformationObject] = field(default_factory=list)
    originator_address: int = 0
    negative: bool = False
    test: bool = False
    sequence: bool = False


_CP24_TYPES = {2, 4, 6, 8, 10, 12, 14, 16, 18, 20}
_CP56_TYPES = {30, 31, 32, 33, 34, 35, 36, 37, 58, 59, 60, 61, 62, 63, 64}
_SINGLE_TYPES = {1, 2, 30, 45, 58}
_DOUBLE_TYPES = {3, 4, 31, 46, 59}
_STEP_TYPES = {5, 6, 32, 47, 60}
_NORMALIZED_TYPES = {9, 10, 21, 34, 48, 61}
_SCALED_TYPES = {11, 12, 35, 49, 62}
_FLOAT_TYPES = {13, 14, 36, 50, 63}
_BITSTRING_TYPES = {7, 8, 33, 51, 64}
_COUNTER_TYPES = {15, 16, 37}
_COMMAND_TYPES = set(range(45, 52)) | set(range(58, 65))


def _encode_uint(value: int, size: int, field_name: str) -> bytes:
    maximum = (1 << (8 * size)) - 1
    if not 0 <= int(value) <= maximum:
        raise ASDUCodecError(f"{field_name} {value} exceeds {size}-byte range")
    return int(value).to_bytes(size, "little")


def _decode_cp24(data: bytes) -> datetime:
    if len(data) != 3:
        raise ASDUCodecError("CP24Time2a requires 3 bytes")
    millis = int.from_bytes(data[:2], "little") & 0x7FFF
    minute = data[2] & 0x3F
    now = datetime.now().astimezone()
    return now.replace(minute=minute, second=millis // 1000, microsecond=(millis % 1000) * 1000)


def _encode_cp24(value: datetime | None) -> bytes:
    value = value or datetime.now().astimezone()
    millis = value.second * 1000 + value.microsecond // 1000
    return millis.to_bytes(2, "little") + bytes([value.minute & 0x3F])


def _decode_cp56(data: bytes) -> datetime:
    if len(data) != 7:
        raise ASDUCodecError("CP56Time2a requires 7 bytes")
    millis = int.from_bytes(data[:2], "little") & 0x7FFF
    minute = data[2] & 0x3F
    hour = data[3] & 0x1F
    day = data[4] & 0x1F
    month = data[5] & 0x0F
    year = 2000 + (data[6] & 0x7F)
    try:
        return datetime(year, month, day, hour, minute, millis // 1000, (millis % 1000) * 1000).astimezone()
    except ValueError as exc:
        raise ASDUCodecError(f"invalid CP56Time2a: {exc}") from exc


def _encode_cp56(value: datetime | None) -> bytes:
    value = value or datetime.now().astimezone()
    millis = value.second * 1000 + value.microsecond // 1000
    weekday = value.isoweekday() & 0x07
    return b"".join(
        (
            millis.to_bytes(2, "little"),
            bytes([value.minute & 0x3F]),
            bytes([value.hour & 0x1F]),
            bytes([(value.day & 0x1F) | (weekday << 5)]),
            bytes([value.month & 0x0F]),
            bytes([(value.year - 2000) & 0x7F]),
        )
    )


class ASDUCodec:
    """Encode/decode IEC 60870-5 ASDUs with configurable field widths."""

    def __init__(self, *, cause_size: int = 2, common_address_size: int = 2, io_address_size: int = 3):
        if cause_size not in (1, 2):
            raise ValueError("cause_size must be 1 or 2")
        if common_address_size not in (1, 2):
            raise ValueError("common_address_size must be 1 or 2")
        if io_address_size not in (1, 2, 3):
            raise ValueError("io_address_size must be 1, 2 or 3")
        self.cause_size = cause_size
        self.common_address_size = common_address_size
        self.io_address_size = io_address_size

    def encode(self, asdu: ASDU) -> bytes:
        if not 0 <= asdu.type_id <= 255:
            raise ASDUCodecError("type_id must fit in one byte")
        if len(asdu.objects) > 127:
            raise ASDUCodecError("an ASDU can contain at most 127 objects")
        if asdu.sequence and not asdu.objects:
            raise ASDUCodecError("sequence ASDU cannot be empty")

        vsq = len(asdu.objects) | (0x80 if asdu.sequence else 0)
        cot = (asdu.cause & 0x3F) | (0x40 if asdu.negative else 0) | (0x80 if asdu.test else 0)
        out = bytearray((asdu.type_id, vsq, cot))
        if self.cause_size == 2:
            out.append(asdu.originator_address & 0xFF)
        out.extend(_encode_uint(asdu.common_address, self.common_address_size, "common address"))

        first_address = asdu.objects[0].io_address if asdu.objects else 0
        for index, obj in enumerate(asdu.objects):
            if not asdu.sequence or index == 0:
                out.extend(_encode_uint(obj.io_address, self.io_address_size, "information object address"))
            elif obj.io_address != first_address + index:
                raise ASDUCodecError("sequence object addresses must be contiguous")
            out.extend(self._encode_object(asdu.type_id, obj))
        return bytes(out)

    def decode(self, data: bytes) -> ASDU:
        header_size = 2 + self.cause_size + self.common_address_size
        if len(data) < header_size:
            raise ASDUCodecError("ASDU header is truncated")
        type_id = data[0]
        vsq = data[1]
        count = vsq & 0x7F
        sequence = bool(vsq & 0x80)
        cot = data[2]
        offset = 3
        originator = data[offset] if self.cause_size == 2 else 0
        if self.cause_size == 2:
            offset += 1
        common_address = int.from_bytes(data[offset : offset + self.common_address_size], "little")
        offset += self.common_address_size
        objects: list[InformationObject] = []
        first_address = 0
        for index in range(count):
            if not sequence or index == 0:
                end = offset + self.io_address_size
                if end > len(data):
                    raise ASDUCodecError("information object address is truncated")
                io_address = int.from_bytes(data[offset:end], "little")
                offset = end
                if index == 0:
                    first_address = io_address
            else:
                io_address = first_address + index
            obj, consumed = self._decode_object(type_id, io_address, data[offset:])
            offset += consumed
            objects.append(obj)
        if offset != len(data):
            raise ASDUCodecError(f"ASDU has {len(data) - offset} trailing byte(s)")
        return ASDU(
            type_id=type_id,
            cause=cot & 0x3F,
            common_address=common_address,
            objects=objects,
            originator_address=originator,
            negative=bool(cot & 0x40),
            test=bool(cot & 0x80),
            sequence=sequence,
        )

    def _encode_object(self, type_id: int, obj: InformationObject) -> bytes:
        if type_id in _SINGLE_TYPES:
            raw = (int(bool(obj.value)) & 0x01) | ((obj.qualifier & 0x1F) << 2)
            if type_id in _COMMAND_TYPES and obj.select:
                raw |= 0x80
            elif type_id not in _COMMAND_TYPES:
                raw |= obj.quality & 0xF0
            value = bytes([raw])
        elif type_id in _DOUBLE_TYPES or type_id in _STEP_TYPES:
            raw = int(obj.value) & 0x03
            if type_id in _COMMAND_TYPES:
                raw |= (obj.qualifier & 0x1F) << 2
                if obj.select:
                    raw |= 0x80
            else:
                raw |= obj.quality & 0xF0
            value = bytes([raw])
        elif type_id in _NORMALIZED_TYPES:
            normalized = max(-1.0, min(1.0, float(obj.value)))
            value = struct.pack("<h", round(normalized * 32767))
            if type_id != 21:
                descriptor = (
                    (obj.qualifier & 0x7F) | (0x80 if obj.select else 0)
                    if type_id in _COMMAND_TYPES
                    else obj.quality & 0xF1
                )
                value += bytes([descriptor])
        elif type_id in _SCALED_TYPES:
            value = struct.pack("<h", int(round(obj.value)))
            descriptor = (
                (obj.qualifier & 0x7F) | (0x80 if obj.select else 0)
                if type_id in _COMMAND_TYPES
                else obj.quality & 0xF1
            )
            value += bytes([descriptor])
        elif type_id in _FLOAT_TYPES:
            value = struct.pack("<f", float(obj.value))
            descriptor = (
                (obj.qualifier & 0x7F) | (0x80 if obj.select else 0)
                if type_id in _COMMAND_TYPES
                else obj.quality & 0xF1
            )
            value += bytes([descriptor])
        elif type_id in _BITSTRING_TYPES:
            value = struct.pack("<I", int(obj.value) & 0xFFFFFFFF)
            descriptor = (
                (obj.qualifier & 0x7F) | (0x80 if obj.select else 0)
                if type_id in _COMMAND_TYPES
                else obj.quality & 0xF1
            )
            value += bytes([descriptor])
        elif type_id in _COUNTER_TYPES:
            value = struct.pack("<i", int(obj.value)) + bytes([obj.quality & 0xFF])
        elif type_id in (100, 101, 103):
            if type_id == 103:
                value = _encode_cp56(obj.timestamp)
            else:
                value = bytes([int(obj.value) & 0xFF])
        elif type_id == 102:
            value = b""
        else:
            type_name = get_iec104_type_by_code(type_id)
            raise ASDUCodecError(f"unsupported ASDU type {type_name or type_id}")

        if type_id in _CP24_TYPES:
            value += _encode_cp24(obj.timestamp)
        elif type_id in _CP56_TYPES:
            value += _encode_cp56(obj.timestamp)
        return value

    def _decode_object(self, type_id: int, io_address: int, data: bytes) -> tuple[InformationObject, int]:
        def require(size: int) -> bytes:
            if len(data) < size:
                raise ASDUCodecError(f"information object for type {type_id} is truncated")
            return data[:size]

        quality = 0
        qualifier = 0
        select = False
        timestamp = None
        if type_id in _SINGLE_TYPES:
            raw = require(1)[0]
            value = raw & 0x01
            consumed = 1
            if type_id in _COMMAND_TYPES:
                qualifier, select = (raw >> 2) & 0x1F, bool(raw & 0x80)
            else:
                quality = raw & 0xF0
        elif type_id in _DOUBLE_TYPES or type_id in _STEP_TYPES:
            raw = require(1)[0]
            value = raw & 0x03
            consumed = 1
            if type_id in _COMMAND_TYPES:
                qualifier, select = (raw >> 2) & 0x1F, bool(raw & 0x80)
            else:
                quality = raw & 0xF0
        elif type_id in _NORMALIZED_TYPES:
            minimum = 2 if type_id == 21 else 3
            raw = require(minimum)
            signed = struct.unpack("<h", raw[:2])[0]
            value = -1.0 if signed == -32768 else signed / 32767.0
            consumed = minimum
            if minimum == 3:
                if type_id in _COMMAND_TYPES:
                    qualifier, select = raw[2] & 0x7F, bool(raw[2] & 0x80)
                else:
                    quality = raw[2]
        elif type_id in _SCALED_TYPES:
            raw = require(3)
            value = struct.unpack("<h", raw[:2])[0]
            consumed = 3
            if type_id in _COMMAND_TYPES:
                qualifier, select = raw[2] & 0x7F, bool(raw[2] & 0x80)
            else:
                quality = raw[2]
        elif type_id in _FLOAT_TYPES:
            raw = require(5)
            value = struct.unpack("<f", raw[:4])[0]
            consumed = 5
            if type_id in _COMMAND_TYPES:
                qualifier, select = raw[4] & 0x7F, bool(raw[4] & 0x80)
            else:
                quality = raw[4]
        elif type_id in _BITSTRING_TYPES:
            raw = require(5)
            value = struct.unpack("<I", raw[:4])[0]
            consumed = 5
            if type_id in _COMMAND_TYPES:
                qualifier, select = raw[4] & 0x7F, bool(raw[4] & 0x80)
            else:
                quality = raw[4]
        elif type_id in _COUNTER_TYPES:
            raw = require(5)
            value, quality, consumed = struct.unpack("<i", raw[:4])[0], raw[4], 5
        elif type_id in (100, 101):
            value, consumed = require(1)[0], 1
        elif type_id == 102:
            value, consumed = None, 0
        elif type_id == 103:
            timestamp, value, consumed = _decode_cp56(require(7)), None, 7
        else:
            info = get_iec104_type_info(str(get_iec104_type_by_code(type_id) or ""))
            raise ASDUCodecError(f"unsupported ASDU type {info.type_id if info else type_id}")

        if type_id in _CP24_TYPES:
            timestamp = _decode_cp24(require(consumed + 3)[consumed : consumed + 3])
            consumed += 3
        elif type_id in _CP56_TYPES:
            timestamp = _decode_cp56(require(consumed + 7)[consumed : consumed + 7])
            consumed += 7
        return InformationObject(io_address, value, quality, timestamp, qualifier, select), consumed
