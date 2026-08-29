import asyncio
from pathlib import Path
from types import SimpleNamespace

from pydnp3_pure.app.constants import CommandStatus, FunctionCode, Qualifier
from pydnp3_pure.app.fragment import ObjectData, build_request, build_response, parse_fragment
from pydnp3_pure.app.header import IIN
from pydnp3_pure.app.object_header import ObjectHeader
from pydnp3_pure.link.frame import LinkFrame
from pydnp3_pure.objects.types import CROB, AnalogPoint
import pytest

from src.device.core.message.parsers.dnp3 import parse_dnp3
from src.proto.dnp3.application import parse_application_fragment
from src.proto.dnp3.dnp3_client import Dnp3Client
from src.proto.dnp3.dnp3_server import Dnp3Server, _OutstationHandler
from src.proto.dnp3.outstation_session import _object_for_points
from src.proto.dnp3.reliable_link import ReliableLinkEndpoint
from src.proto.dnp3.wire import FragmentCorrelator, WireFrameExtractor, accepts_link_address


def test_wire_extractor_preserves_frame_boundaries_for_split_and_sticky_tcp_data():
    first = LinkFrame.create(1, 0, True, 4, b"\xc0\x01").serialize()
    second = LinkFrame.create(1, 0, True, 4, b"\xc1\x01").serialize()
    captured = []
    extractor = WireFrameExtractor(captured.append)

    extractor.data_received(b"noise" + first[:7])
    extractor.data_received(first[7:] + second)

    assert captured == [first, second]
    assert all(parse_dnp3(frame)["valid"] for frame in captured)


def test_fixed_wire_fixture_parses_class0_request_independently_of_frame_builder():
    fixture = Path("tests/fixtures/dnp3/class0_read_request.hex").read_text(encoding="utf-8")
    raw = bytes.fromhex(" ".join(line for line in fixture.splitlines() if not line.startswith("#")))

    parsed = parse_dnp3(raw, role="Request")

    assert parsed["valid"]
    assert parsed["application_function_code"] == int(FunctionCode.READ)
    assert parsed["application_sequence"] == 0
    assert parsed["objects"][0]["dnp3_group"] == 60
    assert parsed["objects"][0]["dnp3_variation"] == 1


def test_parser_preserves_unknown_object_and_recovers_following_known_object():
    application = bytes.fromhex("C0 81 00 00 63 01 07 01 AA 34 02 07 01 05 00")
    raw = LinkFrame.create(0, 1, True, 4, bytes([0xC0]) + application, direction=False).serialize()

    parsed = parse_dnp3(raw, role="Response")

    assert parsed["objects"][0]["dnp3_group"] == 99
    assert parsed["objects"][0]["raw_value"] == "AA"
    assert parsed["objects"][1]["dnp3_group"] == 52
    assert parsed["objects"][1]["value"] == 5


def test_link_address_filter_accepts_exact_and_broadcast_destinations_only():
    assert accepts_link_address(1, 0, local=1, remote=0)
    assert accepts_link_address(0xFFFF, 0, local=1, remote=0)
    assert not accepts_link_address(2, 0, local=1, remote=0)
    assert not accepts_link_address(1, 7, local=1, remote=0)


@pytest.mark.asyncio
async def test_link_confirmation_retries_toggles_fcb_and_deduplicates_received_data():
    written = []
    delivered = []
    endpoint = ReliableLinkEndpoint(
        enabled=True,
        local_is_master=True,
        write_frame=written.append,
        deliver_frame=delivered.append,
        timeout_seconds=0.05,
        max_retries=1,
    )
    outgoing = LinkFrame.create(1, 0, True, 4, b"payload")
    endpoint.send(outgoing)
    assert written[-1].header.function == 3
    assert written[-1].header.fcb is False
    await asyncio.sleep(0.06)
    assert len(written) == 2
    endpoint.on_frame(LinkFrame.create(0, 1, False, 0, direction=False))

    endpoint.send(outgoing)
    assert written[-1].header.fcb is True
    endpoint.on_frame(LinkFrame.create(0, 1, False, 0, direction=False))

    incoming = LinkFrame.create(0, 1, True, 3, b"event", direction=False, fcb=False, fcv=True)
    endpoint.on_frame(incoming)
    endpoint.on_frame(incoming)
    assert [frame.user_data for frame in delivered] == [b"event"]
    endpoint.reset()


def test_transport_segments_share_a_fragment_correlation_id():
    correlator = FragmentCorrelator("rx")
    first = LinkFrame.create(1, 0, True, 4, bytes([0x80 | 7]) + b"part-1").serialize()
    final = LinkFrame.create(1, 0, True, 4, bytes([0x40 | 8]) + b"part-2").serialize()

    first_meta = correlator.metadata(first)
    final_meta = correlator.metadata(final)

    assert first_meta["fragment_correlation_id"] == final_meta["fragment_correlation_id"]
    assert first_meta["transport_first"] is True
    assert first_meta["transport_final"] is False
    assert final_meta["transport_first"] is False
    assert final_meta["transport_final"] is True


def test_selector_parser_keeps_16_bit_read_range_without_consuming_point_values():
    request = build_request(
        FunctionCode.READ,
        5,
        [ObjectData(ObjectHeader(30, 5, Qualifier.RANGE_16_START_STOP, 300, 301, 2))],
    )

    message = parse_application_fragment(request)

    assert message.function == FunctionCode.READ
    assert len(message.objects) == 1
    assert message.objects[0].header.start == 300
    assert message.objects[0].header.stop == 301
    assert message.objects[0].points == []


def test_sparse_and_16_bit_indexes_are_serialized_with_index16():
    points = [
        AnalogPoint(index=1, value=1.0),
        AnalogPoint(index=100, value=2.0),
        AnalogPoint(index=300, value=3.0),
    ]
    obj = _object_for_points(30, 5, points)

    assert obj is not None
    assert obj.header.qualifier == Qualifier.INDEX_16
    parsed = parse_fragment(build_response(0, IIN(), [obj]))
    assert [point.index for point in parsed.objects[0].points] == [1, 100, 300]


def test_outstation_sbo_requires_matching_unexpired_select(monkeypatch):
    server = Dnp3Server()
    server.add_binary_output(300)
    handler = _OutstationHandler(server, server._db, select_timeout_seconds=1)
    on = CROB(control=3, count=1, on_time_ms=0, off_time_ms=0)
    off = CROB(control=4, count=1, on_time_ms=0, off_time_ms=0)

    assert handler.on_operate_binary(300, on) == CommandStatus.NO_SELECT
    assert handler.on_select_binary(300, on) == CommandStatus.SUCCESS
    assert handler.on_operate_binary(300, off) == CommandStatus.NO_SELECT
    assert server.get_binary_output(300) is False

    now = 10.0
    monkeypatch.setattr("src.proto.dnp3.dnp3_server.time.monotonic", lambda: now)
    assert handler.on_select_binary(300, on) == CommandStatus.SUCCESS
    now = 12.0
    assert handler.on_operate_binary(300, on) == CommandStatus.NO_SELECT
    assert server.get_binary_output(300) is False

    assert handler.on_direct_operate_binary(301, on) == CommandStatus.OUT_OF_RANGE
    invalid = CROB(control=0, count=1, on_time_ms=0, off_time_ms=0)
    assert handler.on_direct_operate_binary(300, invalid) == CommandStatus.FORMAT_ERROR


@pytest.mark.asyncio
async def test_master_transaction_retries_timeout_and_ignores_wrong_sequence():
    client = Dnp3Client()
    client._config["runtime"] = {"command_timeout_ms": 20, "max_retries": 1}
    client._client = SimpleNamespace(is_open=True)
    timeouts = []
    client.set_connection_callbacks(on_timeout=timeouts.append)

    class FakeTransport:
        def __init__(self):
            self.sent = 0

        def send_fragment(self, fragment, direction):
            self.sent += 1
            request = parse_application_fragment(fragment)
            loop = asyncio.get_running_loop()
            if self.sent == 1:
                wrong = parse_fragment(build_response((request.header.control.seq + 1) & 0x0F, IIN(), []))
                loop.call_soon(client._on_app_message, wrong)
            else:
                response = parse_fragment(build_response(request.header.control.seq, IIN(), []))
                loop.call_soon(client._on_app_message, response)

    transport = FakeTransport()
    client._transport = transport
    response = await client._request(
        FunctionCode.READ,
        [ObjectData(ObjectHeader(60, 1, Qualifier.ALL_POINTS, 0, 0, 0))],
    )

    assert response.function == FunctionCode.RESPONSE
    assert transport.sent == 2
    assert len(timeouts) == 1
    assert timeouts[0].attempt == 0


@pytest.mark.asyncio
async def test_default_master_outstation_tcp_round_trip_read_control_and_capture():
    server = Dnp3Server()
    server.set_server_ip("127.0.0.1")
    server.set_server_port(0)
    server.set_parameters(link_confirm=True, link_confirm_timeout_ms=100)
    for index, value in ((1, 11.0), (100, 22.0), (300, 33.0)):
        server.add_analog_input(index)
        server.update_analog_input(index, value)
    server.add_binary_output(300)

    client = Dnp3Client()
    client.set_server_ip("127.0.0.1")
    client.set_parameters(
        command_timeout_ms=500,
        max_retries=1,
        link_confirm=True,
        link_confirm_timeout_ms=100,
    )

    assert await server.start()
    assert server._server is not None and server._server._server is not None
    port = server._server._server.sockets[0].getsockname()[1]
    client.set_server_port(port)
    try:
        assert await client.start()
        assert await client.read_point_active(300, 30) == pytest.approx(33.0)

        values = await client.read_points_active([(1, 30), (100, 30), (300, 30)])
        assert values == {(1, 30): 11.0, (100, 30): 22.0, (300, 30): 33.0}

        assert await client.operate_only_binary(300, True) is False
        assert client.last_command_statuses == [int(CommandStatus.NO_SELECT)]
        assert await client.select_binary(300, True)
        assert await client.operate_only_binary(300, False) is False
        assert server.get_binary_output(300) is False
        assert await client.select_binary(300, True)
        assert await client.operate_only_binary(300, True)
        assert server.get_binary_output(300) is True
        assert await client.write_binary_direct(301, True) is False
        assert client.last_command_statuses == [int(CommandStatus.OUT_OF_RANGE)]

        captures = client.get_captured_messages()
        assert captures
        rx_frames = [bytes.fromhex(item["data"]) for item in captures if item["direction"] == "RX"]
        assert rx_frames and all(frame.startswith(b"\x05\x64") for frame in rx_frames)
        assert all(parse_dnp3(frame)["valid"] for frame in rx_frames)
    finally:
        await client.stop()
        await server.stop()


@pytest.mark.asyncio
async def test_master_reconnects_after_outstation_restart_and_resets_session():
    server = Dnp3Server()
    server.set_server_ip("127.0.0.1")
    server.set_server_port(0)
    server.add_analog_input(300)
    server.update_analog_input(300, 44.0)
    assert await server.start()
    assert server._server is not None and server._server._server is not None
    port = server._server._server.sockets[0].getsockname()[1]

    client = Dnp3Client()
    states = []
    client.set_server_ip("127.0.0.1")
    client.set_server_port(port)
    client.set_parameters(
        command_timeout_ms=500,
        max_retries=0,
        reconnect_initial_interval_ms=20,
        reconnect_max_interval_ms=50,
        reconnect_max_attempts=-1,
    )
    client.set_connection_callbacks(
        on_connect=lambda remote, local: states.append("connected"),
        on_disconnect=lambda reason, detail: states.append("disconnected"),
    )

    try:
        assert await client.start()
        assert await client.read_point_active(300, 30) == pytest.approx(44.0)
        await server.stop()
        for _ in range(100):
            if "disconnected" in states:
                break
            await asyncio.sleep(0.01)
        assert "disconnected" in states

        server.set_server_port(port)
        assert await server.start()
        for _ in range(100):
            if states.count("connected") >= 2:
                break
            await asyncio.sleep(0.01)
        assert states.count("connected") >= 2
        assert await client.read_point_active(300, 30) == pytest.approx(44.0)
    finally:
        await client.stop()
        await server.stop()


@pytest.mark.asyncio
async def test_event_poll_is_confirmed_once_and_preserves_timestamp_metadata():
    server = Dnp3Server()
    server.set_server_ip("127.0.0.1")
    server.set_server_port(0)
    server.set_parameters(app_confirm=True, confirm_timeout_ms=100, confirm_max_retries=1)
    server.add_analog_input(9, event_class=1)
    assert await server.start()
    assert server._server is not None and server._server._server is not None
    port = server._server._server.sockets[0].getsockname()[1]

    client = Dnp3Client()
    client.set_server_ip("127.0.0.1")
    client.set_server_port(port)
    client.set_parameters(command_timeout_ms=500, max_retries=0)
    try:
        assert await client.start()
        server.update_analog_input(9, 12.5)
        assert await client.send_event_poll((1,))
        for _ in range(50):
            assert server._session is not None
            if not server._session._events.has_events:
                break
            await asyncio.sleep(0.01)
        assert not server._session._events.has_events
        metadata = client.read_point_metadata(9, 32)
        assert metadata is not None
        assert metadata["source"] == "solicited"
        assert metadata["timestamp"] is not None

        captured_count = len(client.get_captured_messages())
        assert await client.send_event_poll((1,))
        assert len(client.get_captured_messages()) == captured_count + 2
    finally:
        await client.stop()
        await server.stop()


@pytest.mark.asyncio
async def test_unsolicited_event_updates_master_cache_and_is_confirmed():
    server = Dnp3Server()
    server.set_server_ip("127.0.0.1")
    server.set_server_port(0)
    server.set_parameters(enable_unsolicited=True, app_confirm=True, confirm_timeout_ms=100)
    server.add_binary_input(12, event_class=2)
    assert await server.start()
    assert server._server is not None and server._server._server is not None
    port = server._server._server.sockets[0].getsockname()[1]

    client = Dnp3Client()
    client.set_server_ip("127.0.0.1")
    client.set_server_port(port)
    client.set_parameters(command_timeout_ms=500, max_retries=0, enable_unsolicited=True)
    try:
        assert await client.start()
        server.update_binary_input(12, True)
        for _ in range(100):
            if client.read_point(12, 2) is True:
                break
            await asyncio.sleep(0.01)
        assert client.read_point(12, 2) is True
        metadata = client.read_point_metadata(12, 2)
        assert metadata is not None and metadata["source"] == "unsolicited"
        for _ in range(50):
            assert server._session is not None
            if not server._session._events.has_events:
                break
            await asyncio.sleep(0.01)
        assert not server._session._events.has_events
    finally:
        await client.stop()
        await server.stop()


@pytest.mark.asyncio
async def test_time_restart_and_counter_freeze_round_trip():
    server = Dnp3Server()
    server.set_server_ip("127.0.0.1")
    server.set_server_port(0)
    server._db.add_counter(7, 42)
    assert await server.start()
    assert server._server is not None and server._server._server is not None

    client = Dnp3Client()
    client.set_server_ip("127.0.0.1")
    client.set_server_port(server._server._server.sockets[0].getsockname()[1])
    client.set_parameters(command_timeout_ms=500, max_retries=0)
    try:
        assert await client.start()
        assert await client.measure_delay() is not None
        assert await client.sync_time()
        assert await client.warm_restart() == 0
        assert await client.cold_restart() == 0
        assert await client.freeze_counters(7, 7)
        assert server._db.get_frozen_counters(7, 7)[0].value == 42
        assert await client.freeze_counters(7, 7, clear=True)
        assert server._db.get_counters(7, 7)[0].value == 0
        assert await client.freeze_counters(7, 7, no_ack=True)
    finally:
        await client.stop()
        await server.stop()


def test_point_level_config_controls_event_policy_variations_and_quality():
    server = Dnp3Server()
    server.add_analog_input(
        8,
        dnp3_config={
            "static_variation": 3,
            "event_variation": 5,
            "event_class": 2,
            "deadband": 10,
            "initial_quality": 5,
            "event_enabled": False,
            "timestamp_enabled": False,
        },
    )

    point = server._db.get_analog_inputs(8, 8)[0]
    config = server._db._ai_config[8]
    assert point.flags == 5
    assert config.default_variation == 3
    assert config.event_variation == 5
    assert config.event_class == 2
    assert config.deadband == 10
    assert config.event_enabled is False
    assert config.timestamp_enabled is False


def test_point_indexes_outside_dnp3_16_bit_range_are_rejected():
    server = Dnp3Server()
    with pytest.raises(ValueError, match="65535"):
        server.add_analog_input(65536)
    with pytest.raises(ValueError, match="65535"):
        Dnp3Client().set_addresses(-1, 1)
