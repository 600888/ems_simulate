"""IEC 60870-5-101 FT1.2 link-layer framing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class FT12Error(ValueError):
    pass


class PrimaryFunction(IntEnum):
    RESET_REMOTE_LINK = 0
    RESET_USER_PROCESS = 1
    SEND_CONFIRMED_USER_DATA = 3
    SEND_UNCONFIRMED_USER_DATA = 4
    REQUEST_LINK_STATUS = 9
    REQUEST_CLASS_1 = 10
    REQUEST_CLASS_2 = 11


class SecondaryFunction(IntEnum):
    ACK = 0
    NACK = 1
    USER_DATA = 8
    NO_DATA = 9
    LINK_STATUS = 11


@dataclass(frozen=True, slots=True)
class ControlField:
    function: int
    primary: bool
    direction: bool = False
    fcb_acd: bool = False
    fcv_dfc: bool = False

    def encode(self) -> int:
        return (
            (0x80 if self.direction else 0)
            | (0x40 if self.primary else 0)
            | (0x20 if self.fcb_acd else 0)
            | (0x10 if self.fcv_dfc else 0)
            | (self.function & 0x0F)
        )

    @classmethod
    def decode(cls, value: int) -> ControlField:
        return cls(value & 0x0F, bool(value & 0x40), bool(value & 0x80), bool(value & 0x20), bool(value & 0x10))


@dataclass(frozen=True, slots=True)
class FT12Frame:
    control: ControlField | None = None
    link_address: int = 0
    user_data: bytes = b""
    single_char_ack: bool = False

    @property
    def variable(self) -> bool:
        return bool(self.user_data)


class FT12Codec:
    def __init__(self, *, link_address_size: int = 1):
        if link_address_size not in (1, 2):
            raise ValueError("link_address_size must be 1 or 2")
        self.link_address_size = link_address_size

    @staticmethod
    def checksum(data: bytes) -> int:
        return sum(data) & 0xFF

    def encode_fixed(self, control: ControlField, link_address: int) -> bytes:
        body = bytes([control.encode()]) + link_address.to_bytes(self.link_address_size, "little")
        return b"\x10" + body + bytes([self.checksum(body), 0x16])

    def encode_variable(self, control: ControlField, link_address: int, user_data: bytes) -> bytes:
        body = bytes([control.encode()]) + link_address.to_bytes(self.link_address_size, "little") + bytes(user_data)
        if len(body) > 255:
            raise FT12Error("FT1.2 variable frame body exceeds 255 bytes")
        length = len(body)
        return bytes([0x68, length, length, 0x68]) + body + bytes([self.checksum(body), 0x16])

    @staticmethod
    def encode_ack() -> bytes:
        return b"\xe5"

    def decode(self, data: bytes) -> FT12Frame:
        if data == b"\xe5":
            return FT12Frame(single_char_ack=True)
        if not data:
            raise FT12Error("empty FT1.2 frame")
        if data[0] == 0x10:
            expected = self.link_address_size + 4
            if len(data) != expected or data[-1] != 0x16:
                raise FT12Error("invalid fixed FT1.2 frame length or terminator")
            body = data[1 : 2 + self.link_address_size]
            if self.checksum(body) != data[-2]:
                raise FT12Error("fixed FT1.2 checksum mismatch")
            return FT12Frame(ControlField.decode(body[0]), int.from_bytes(body[1:], "little"))
        if data[0] == 0x68:
            if len(data) < 7 or data[1] != data[2] or data[3] != 0x68:
                raise FT12Error("invalid variable FT1.2 header")
            length = data[1]
            if len(data) != length + 6 or data[-1] != 0x16:
                raise FT12Error("invalid variable FT1.2 frame length or terminator")
            body = data[4 : 4 + length]
            if len(body) < 1 + self.link_address_size:
                raise FT12Error("variable FT1.2 body is truncated")
            if self.checksum(body) != data[-2]:
                raise FT12Error("variable FT1.2 checksum mismatch")
            address_end = 1 + self.link_address_size
            return FT12Frame(
                ControlField.decode(body[0]),
                int.from_bytes(body[1:address_end], "little"),
                body[address_end:],
            )
        raise FT12Error(f"unknown FT1.2 start byte 0x{data[0]:02X}")


class FT12StreamDecoder:
    """Incremental decoder that also resynchronizes after line noise."""

    def __init__(self, codec: FT12Codec):
        self.codec = codec
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[tuple[bytes, FT12Frame]]:
        self._buffer.extend(data)
        frames: list[tuple[bytes, FT12Frame]] = []
        while self._buffer:
            start = self._buffer[0]
            if start == 0xE5:
                raw = bytes(self._buffer[:1])
                del self._buffer[:1]
            elif start == 0x10:
                size = self.codec.link_address_size + 4
                if len(self._buffer) < size:
                    break
                raw = bytes(self._buffer[:size])
                del self._buffer[:size]
            elif start == 0x68:
                if len(self._buffer) < 4:
                    break
                if self._buffer[1] != self._buffer[2] or self._buffer[3] != 0x68:
                    del self._buffer[:1]
                    continue
                size = self._buffer[1] + 6
                if len(self._buffer) < size:
                    break
                raw = bytes(self._buffer[:size])
                del self._buffer[:size]
            else:
                del self._buffer[:1]
                continue
            try:
                frames.append((raw, self.codec.decode(raw)))
            except FT12Error:
                continue
        return frames
