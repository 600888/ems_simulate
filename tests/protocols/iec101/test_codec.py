"""IEC 60870-5-101 application/link-layer conformance tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from src.proto.iec101.ft12 import (
    ControlField,
    FT12Codec,
    FT12Error,
    FT12StreamDecoder,
    PrimaryFunction,
    SecondaryFunction,
)
from src.proto.iec101.server import IEC101Slave
from src.proto.iec60870.asdu import ASDU, ASDUCodec, InformationObject


def test_fixed_frame_matches_ft12_known_vector():
    codec = FT12Codec(link_address_size=1)
    raw = codec.encode_fixed(
        ControlField(PrimaryFunction.REQUEST_LINK_STATUS, primary=True),
        1,
    )
    assert raw == bytes.fromhex("10 49 01 4A 16")
    frame = codec.decode(raw)
    assert frame.control == ControlField(PrimaryFunction.REQUEST_LINK_STATUS, primary=True)
    assert frame.link_address == 1


def test_variable_frame_round_trip_and_checksum_rejection():
    codec = FT12Codec(link_address_size=2)
    control = ControlField(
        PrimaryFunction.SEND_CONFIRMED_USER_DATA,
        primary=True,
        fcb_acd=True,
        fcv_dfc=True,
    )
    raw = codec.encode_variable(control, 0x1234, bytes.fromhex("64 01 06 00"))
    decoded = codec.decode(raw)
    assert decoded.control == control
    assert decoded.link_address == 0x1234
    assert decoded.user_data == bytes.fromhex("64 01 06 00")

    damaged = bytearray(raw)
    damaged[-2] ^= 0x01
    with pytest.raises(FT12Error, match="checksum"):
        codec.decode(bytes(damaged))


def test_stream_decoder_resynchronizes_after_noise_and_fragmentation():
    codec = FT12Codec(link_address_size=1)
    decoder = FT12StreamDecoder(codec)
    fixed = codec.encode_fixed(ControlField(PrimaryFunction.REQUEST_CLASS_1, primary=True), 2)
    assert decoder.feed(b"\x00\xff" + fixed[:2]) == []
    frames = decoder.feed(fixed[2:] + b"\xe5")
    assert [raw for raw, _ in frames] == [fixed, b"\xe5"]


def test_general_interrogation_asdu_matches_known_vector():
    codec = ASDUCodec(cause_size=2, common_address_size=2, io_address_size=3)
    asdu = ASDU(100, 6, 1, [InformationObject(0, 20)])
    raw = codec.encode(asdu)
    assert raw == bytes.fromhex("64 01 06 00 01 00 00 00 00 14")
    assert codec.decode(raw) == asdu


@pytest.mark.parametrize(
    "function",
    [PrimaryFunction.REQUEST_CLASS_1, PrimaryFunction.REQUEST_CLASS_2],
)
def test_slave_reports_empty_class_with_no_data_fixed_frame(function: PrimaryFunction):
    slave = IEC101Slave(port="unused", link_addresses=[1])
    link_codec = FT12Codec()
    request = link_codec.decode(link_codec.encode_fixed(ControlField(function, primary=True), 1))

    raw = slave.handle_frame(request)
    assert raw != b"\xe5"
    response = link_codec.decode(raw)
    assert response.control == ControlField(
        SecondaryFunction.NO_DATA,
        primary=False,
        direction=True,
    )


def test_slave_ack_advertises_pending_class_one_data():
    slave = IEC101Slave(port="unused", link_addresses=[1])
    asdu_codec = ASDUCodec()
    link_codec = FT12Codec()
    request = ASDU(100, 6, 1, [InformationObject(0, 20)])
    request_frame = link_codec.decode(
        link_codec.encode_variable(
            ControlField(
                PrimaryFunction.SEND_CONFIRMED_USER_DATA,
                primary=True,
                fcv_dfc=True,
            ),
            1,
            asdu_codec.encode(request),
        )
    )

    raw = slave.handle_frame(request_frame)
    assert raw != b"\xe5"
    response = link_codec.decode(raw)
    assert response.control == ControlField(
        SecondaryFunction.ACK,
        primary=False,
        direction=True,
        fcb_acd=True,
    )


@pytest.mark.parametrize(
    ("type_id", "value", "quality"),
    [
        (1, 1, 0x80),
        (3, 2, 0x10),
        (9, 0.5, 0x01),
        (11, -123, 0x80),
        (13, 12.5, 0x10),
        (15, 123456, 0x20),
        (45, 1, 0),
        (50, 8.25, 0),
    ],
)
def test_asdu_value_types_round_trip(type_id: int, value, quality: int):
    codec = ASDUCodec()
    original = ASDU(type_id, 3, 7, [InformationObject(0x10203, value, quality)])
    decoded = codec.decode(codec.encode(original))
    assert decoded.type_id == type_id
    assert decoded.common_address == 7
    assert decoded.objects[0].io_address == 0x10203
    assert decoded.objects[0].value == pytest.approx(value, abs=1 / 32767)
    assert decoded.objects[0].quality == quality


def test_cp56_timestamp_round_trip():
    codec = ASDUCodec()
    timestamp = datetime(2026, 8, 30, 15, 4, 5, 123000).astimezone()
    original = ASDU(36, 3, 1, [InformationObject(8, 1.25, timestamp=timestamp)])
    decoded = codec.decode(codec.encode(original))
    assert decoded.objects[0].value == pytest.approx(1.25)
    assert decoded.objects[0].timestamp.replace(tzinfo=None) == timestamp.replace(tzinfo=None)


def test_slave_general_interrogation_queues_confirmation_data_and_termination():
    slave = IEC101Slave(port="unused", link_addresses=[1])
    slave.add_point(1, 100, 13, lambda: (12.5, 0))
    asdu_codec = ASDUCodec()
    link_codec = FT12Codec(link_address_size=1)
    request = ASDU(100, 6, 1, [InformationObject(0, 20)])
    request_frame = link_codec.decode(
        link_codec.encode_variable(
            ControlField(PrimaryFunction.SEND_CONFIRMED_USER_DATA, primary=True, fcv_dfc=True),
            1,
            asdu_codec.encode(request),
        )
    )
    acknowledgement = link_codec.decode(slave.handle_frame(request_frame))
    assert acknowledgement.control.function == SecondaryFunction.ACK
    assert acknowledgement.control.fcb_acd is True

    responses = []
    for class_one in (True, False, True):
        function = PrimaryFunction.REQUEST_CLASS_1 if class_one else PrimaryFunction.REQUEST_CLASS_2
        poll = link_codec.decode(link_codec.encode_fixed(ControlField(function, primary=True), 1))
        raw = slave.handle_frame(poll)
        frame = link_codec.decode(raw)
        assert frame.control.function == SecondaryFunction.USER_DATA
        responses.append(asdu_codec.decode(frame.user_data))

    assert [(item.type_id, item.cause) for item in responses] == [(100, 7), (13, 20), (100, 10)]
    assert responses[1].objects[0].value == pytest.approx(12.5)


def test_slave_command_invokes_callback_and_queues_activation_confirmation():
    slave = IEC101Slave(port="unused", link_addresses=[1])
    received = []
    slave.set_command_callback(
        lambda asdu, obj: received.append((asdu.common_address, obj.io_address, obj.value)) or True
    )
    asdu_codec = ASDUCodec()
    link_codec = FT12Codec()
    command = ASDU(45, 6, 1, [InformationObject(42, 1)])
    frame = link_codec.decode(
        link_codec.encode_variable(
            ControlField(PrimaryFunction.SEND_CONFIRMED_USER_DATA, primary=True, fcv_dfc=True),
            1,
            asdu_codec.encode(command),
        )
    )
    acknowledgement = link_codec.decode(slave.handle_frame(frame))
    assert acknowledgement.control.function == SecondaryFunction.ACK
    assert acknowledgement.control.fcb_acd is True
    assert received == [(1, 42, 1)]

    poll = link_codec.decode(link_codec.encode_fixed(ControlField(PrimaryFunction.REQUEST_CLASS_1, primary=True), 1))
    response = link_codec.decode(slave.handle_frame(poll))
    confirmation = asdu_codec.decode(response.user_data)
    assert (confirmation.type_id, confirmation.cause, confirmation.negative) == (45, 7, False)


def test_large_interrogation_is_split_into_valid_ft12_frames():
    slave = IEC101Slave(port="unused", link_addresses=[1])
    for address in range(100):
        slave.add_point(1, address, 13, lambda address=address: (float(address), 0))
    slave._handle_user_data(1, ASDUCodec().encode(ASDU(100, 6, 1, [InformationObject(0, 20)])))
    batches = list(slave._class2[1])
    assert len(batches) > 1
    assert sum(len(asdu.objects) for asdu in batches) == 100
    for asdu in batches:
        raw = slave.codec.encode_variable(
            ControlField(SecondaryFunction.USER_DATA, primary=False),
            1,
            slave.asdu_codec.encode(asdu),
        )
        assert len(raw) <= 261
