from dataclasses import replace
import socket
import sys
import threading
import time
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.proto.iec61850.plugins.goose import capture as capture_module
from src.proto.iec61850.plugins.goose.capture import CapturedPacket, GooseCaptureEngine
from src.proto.iec61850.plugins.goose.types import ReceiverConfig


class _TimeoutSocket:
    def settimeout(self, _timeout):
        pass

    def recv(self, _size):
        time.sleep(0.01)
        raise TimeoutError

    def close(self):
        pass


def _tlv(tag: int, value: bytes) -> bytes:
    assert len(value) < 0x80
    return bytes([tag, len(value)]) + value


def _goose_frame() -> bytes:
    pdu_fields = b"".join(
        [
            _tlv(0x80, b"LD0/LLN0$GO$gcb1"),
            _tlv(0x81, b"\x03\xe8"),
            _tlv(0x82, b"LD0/LLN0$dsGOOSE1"),
            _tlv(0x83, b"gcb1"),
            _tlv(0x84, b"\x00\x00\x00\x01" + bytes(4)),
            _tlv(0x85, b"\x01"),
            _tlv(0x86, b"\x02"),
            _tlv(0x87, b"\x00"),
            _tlv(0x88, b"\x01"),
            _tlv(0x89, b"\x00"),
            _tlv(0x8A, b"\x01"),
            _tlv(0xAB, _tlv(0x83, b"\x01")),
        ]
    )
    pdu = _tlv(0x61, pdu_fields)
    ethernet = bytes.fromhex("010ccd010001 020304050607 88b8")
    goose_header = bytes.fromhex("0001") + (len(pdu) + 8).to_bytes(2, "big") + bytes(4)
    return ethernet + goose_header + pdu


def test_capture_start_keeps_thread_running_until_stop(monkeypatch):
    monkeypatch.setattr(capture_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(capture_module._RawSocketProvider, "create", lambda _interface: _TimeoutSocket())

    engine = GooseCaptureEngine(interface="eth-test")

    assert engine.start() is True
    assert engine.is_running is True

    engine.stop()

    assert engine.is_running is False


def test_capture_processes_goose_frame():
    engine = GooseCaptureEngine(interface="eth-test")

    engine._process_packet(_goose_frame())

    packets = engine.get_packets()
    assert len(packets) == 1
    assert packets[0]["app_id"] == 1
    assert packets[0]["go_cb_ref"] == "LD0/LLN0$GO$gcb1"
    assert packets[0]["data_values"][0]["type"] == "boolean"
    assert packets[0]["data_values"][0]["value"] is True
    assert packets[0]["data_values"][0]["offset"] > 0
    assert packets[0]["fields"]


def test_bad_frames_do_not_replace_subscription_data_and_padding_is_allowed():
    from src.proto.iec61850.plugins.goose.subscriber import GooseReceiver

    ref = "LD0/LLN0$GO$gcb1"
    receiver = GooseReceiver(ReceiverConfig(interface="eth-test"))
    receiver.add_subscription(ref)
    capture = GooseCaptureEngine(interface="eth-test")
    capture.set_callback(receiver._on_captured_packet)
    frame = _goose_frame()

    capture._process_packet(frame + bytes(4))
    before = receiver.get_subscription(ref)
    assert before["state"] == "connected"
    capture._process_packet(frame[:-5])
    capture._process_packet(frame.replace(bytes.fromhex("8a 01 01"), bytes.fromhex("8a 01 02")))

    assert len(capture.get_packets()) == 1
    assert receiver.get_subscription(ref) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("api", ["rest", "websocket"])
@pytest.mark.parametrize("filter_app_id", [None, 0, 0x1001])
async def test_capture_start_replaces_previous_appid_filter(monkeypatch, api, filter_app_id):
    from src.web.api import network_interfaces
    from src.web.api.channel import goose
    from src.web.api.channel.goose_websocket import WebSocketSessionManager
    from src.web.api.schemas.goose import GooseCaptureStartRequest

    capture = GooseCaptureEngine(interface="WLAN")
    capture.set_app_id_filter(1)
    monkeypatch.setattr(capture, "start", Mock(return_value=True))
    monkeypatch.setattr(network_interfaces, "validate_network_interface", Mock())
    params = {"channel_id": 7, "interface": "WLAN", "filter_app_id": filter_app_id}
    if api == "rest":
        monkeypatch.setattr(goose, "_validate_iec61850_channel", Mock())
        monkeypatch.setattr(goose, "_get_capture", lambda *_: capture)
        await goose.start_goose_capture(GooseCaptureStartRequest(**params))
    else:
        monkeypatch.setattr(goose, "GOOSE_CAPTURE_INSTANCES", {"7:WLAN": capture})
        monkeypatch.setattr(WebSocketSessionManager, "_instance", None)
        await WebSocketSessionManager()._handle_start(
            SimpleNamespace(send_text=AsyncMock()), params, GooseCaptureEngine
        )

    assert capture._filter_app_id == filter_app_id
    frame = _goose_frame()
    capture._process_packet(frame[:14] + b"\x10\x01" + frame[16:])
    assert len(capture.get_packets()) == (0 if filter_app_id == 0 else 1)


def test_windows_capture_reuses_socket_and_preserves_queued_sequences(monkeypatch):
    from scapy.automaton import ObjectPipe
    from scapy.packet import Raw
    from scapy.sendrecv import sniff

    engine = GooseCaptureEngine(interface="eth-test")
    frames = [Raw(_goose_frame().replace(b"\x86\x01\x02", bytes([0x86, 1, seq]))) for seq in range(9)]
    capture_socket = ObjectPipe("test capture")
    for frame in frames:
        capture_socket.send(frame)
    capture_socket.close = Mock(wraps=capture_socket.close)

    def open_socket(**kwargs):
        assert kwargs == {"iface": "eth-test"}
        assert not engine.is_running
        assert not engine._started_event.is_set()
        return capture_socket

    def sniff_continuously(**kwargs):
        assert kwargs["opened_socket"][capture_socket] == "capture"
        assert "iface" not in kwargs
        assert "timeout" not in kwargs
        assert engine.is_running
        assert engine._started_event.is_set()
        return sniff(**kwargs)

    scapy = ModuleType("scapy.all")
    scapy.Raw = Raw
    scapy.conf = SimpleNamespace(L2listen=Mock(side_effect=open_socket))
    scapy.sniff = Mock(side_effect=sniff_continuously)
    monkeypatch.setitem(sys.modules, "scapy.all", scapy)
    received = []

    def on_packet(packet):
        received.append(packet.sq_num)
        if len(received) == 9:
            engine.signal_stop()

    engine.set_callback(on_packet)

    assert engine._capture_loop_scapy() is True
    assert received == list(range(9))
    assert [packet["sq_num"] for packet in engine.get_packets()] == list(range(9))
    scapy.conf.L2listen.assert_called_once_with(iface="eth-test")
    scapy.sniff.assert_called_once()
    capture_socket.close.assert_called_once()
    assert not engine.is_running


@pytest.mark.parametrize("failure", ["open", "read"])
def test_windows_capture_cleans_up_after_socket_failure(monkeypatch, failure):
    from scapy.packet import Raw

    engine = GooseCaptureEngine(interface="eth-test")
    capture_socket = Mock()
    scapy = ModuleType("scapy.all")
    scapy.Raw = Raw
    scapy.conf = SimpleNamespace(L2listen=Mock(return_value=capture_socket))
    scapy.sniff = Mock(side_effect=OSError("capture failed"))
    if failure == "open":
        scapy.conf.L2listen.side_effect = OSError("adapter unavailable")
    monkeypatch.setitem(sys.modules, "scapy.all", scapy)

    assert engine._capture_loop_scapy() is False
    assert not engine.is_running
    assert engine._started_event.is_set()
    if failure == "open":
        scapy.sniff.assert_not_called()
        capture_socket.close.assert_not_called()
    else:
        capture_socket.close.assert_called_once()
    assert engine._stop_notifier is None


@pytest.mark.parametrize("stop_mode", ["signal", "blocking", "restart"])
def test_windows_idle_capture_stops_on_notification_and_can_restart(monkeypatch, stop_mode):
    from scapy.automaton import ObjectPipe
    from scapy.packet import Raw
    from scapy.sendrecv import sniff

    sockets = []
    stop_pipes = []

    def open_socket(**_kwargs):
        capture_socket = ObjectPipe("idle capture")
        sockets.append(capture_socket)
        return capture_socket

    def capture(**kwargs):
        assert "timeout" not in kwargs
        stop_pipes.extend(sock for sock, label in kwargs["opened_socket"].items() if label == "stop")
        return sniff(**kwargs)

    scapy = ModuleType("scapy.all")
    scapy.Raw = Raw
    scapy.conf = SimpleNamespace(L2listen=Mock(side_effect=open_socket))
    scapy.sniff = Mock(side_effect=capture)
    monkeypatch.setitem(sys.modules, "scapy.all", scapy)
    monkeypatch.setattr(capture_module.platform, "system", lambda: "Windows")
    engine = GooseCaptureEngine(interface="eth-test")

    for _ in range(2):
        try:
            assert engine.start()
            if stop_mode == "blocking":
                engine.stop()
            else:
                engine.signal_stop()
                engine.signal_stop()  # Repeated notifications are harmless.
                if stop_mode == "restart":
                    previous_worker = engine._capture_thread
                    assert engine.start()
                    assert not previous_worker.is_alive()
                    engine.stop()
                else:
                    engine._capture_thread.join(timeout=0.5)
            assert not engine._capture_thread.is_alive()
            assert not engine.is_running
            assert engine._stop_notifier is None
            assert engine.get_packets() == []  # Stop messages are not captured frames.
        finally:
            engine.stop()

    expected_starts = 4 if stop_mode == "restart" else 2
    assert len(sockets) == expected_starts
    assert len(stop_pipes) == expected_starts
    assert all(sock.closed for sock in sockets + stop_pipes)


@pytest.mark.parametrize("stop_timing", ["opening", "before_wait"])
def test_windows_capture_preserves_stop_notification_during_startup(monkeypatch, stop_timing):
    from scapy.automaton import ObjectPipe
    from scapy.packet import Raw
    from scapy.sendrecv import sniff

    engine = GooseCaptureEngine(interface="eth-test")
    capture_socket = ObjectPipe("opening capture")

    def open_socket(**_kwargs):
        if stop_timing == "opening":
            engine.signal_stop()
        return capture_socket

    def capture(**kwargs):
        # Stop after the notifier is installed but before sniff begins waiting.
        engine.signal_stop()
        return sniff(**kwargs)

    scapy = ModuleType("scapy.all")
    scapy.Raw = Raw
    scapy.conf = SimpleNamespace(L2listen=Mock(side_effect=open_socket))
    scapy.sniff = Mock(side_effect=capture)
    monkeypatch.setitem(sys.modules, "scapy.all", scapy)

    assert engine._capture_loop_scapy() is True
    if stop_timing == "opening":
        scapy.sniff.assert_not_called()
    else:
        scapy.sniff.assert_called_once()
    assert capture_socket.closed
    assert not engine.is_running
    assert engine._started_event.is_set()
    assert engine._stop_notifier is None
    assert engine.get_packets() == []


@pytest.mark.parametrize("vlan_tag", [b"", bytes.fromhex("8100 8000"), bytes.fromhex("8100 8064")])
def test_linux_receiver_reads_local_goose_from_bound_packet_socket(monkeypatch, vlan_tag):
    from src.proto.iec61850.plugins.goose.subscriber import GooseReceiver

    frame = _goose_frame()
    frame = frame[:12] + vlan_tag + frame[12:]
    app_id_offset = 14 + len(vlan_tag)
    wrong_app_id = frame[:app_id_offset] + b"\x00\x02" + frame[app_id_offset + 2 :]
    wrong_mac = bytes.fromhex("010ccd010002") + frame[6:]
    frames = iter([frame[: app_id_offset + 8], wrong_app_id, wrong_mac, frame])
    raw_socket = Mock(spec=_TimeoutSocket, wraps=_TimeoutSocket())
    raw_socket.bind = Mock()
    raw_socket.setsockopt = Mock()
    raw_socket.recv.side_effect = lambda size: next(frames, None) or _TimeoutSocket().recv(size)
    create_socket = Mock(return_value=raw_socket)
    monkeypatch.setattr(capture_module.platform, "system", lambda: "Linux")
    monkeypatch.setattr(socket, "AF_PACKET", 17, raising=False)
    monkeypatch.setattr(socket, "socket", create_socket)
    monkeypatch.setattr(socket, "if_nametoindex", lambda _interface: 7)

    receiver = GooseReceiver(ReceiverConfig(interface="eth-test"))
    ref = "LD0/LLN0$GO$gcb1"
    receiver.add_subscription(ref, app_id=1, dst_mac=[0x01, 0x0C, 0xCD, 0x01, 0x00, 0x01])
    received = threading.Event()
    receiver.set_callback(lambda _packet: received.set())

    try:
        assert receiver.start()
        assert received.wait(2)
        latest = receiver.get_subscription(ref)
        assert latest["state"] == "connected"
        assert latest["message_count"] == 1
        assert latest["timestamp"] == 1000
        assert receiver.get_history(ref)[0]["data_values"][0]["value"] is True
        create_socket.assert_called_once_with(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
        raw_socket.bind.assert_called_once_with(("eth-test", 3))
        raw_socket.setsockopt.assert_called_once()
    finally:
        receiver.stop()

    raw_socket.close.assert_called_once()


def test_goose_receiver_keeps_subscriber_handles(monkeypatch):
    from src.proto.iec61850.plugins.goose import subscriber as subscriber_module

    class FakeIec61850:
        @staticmethod
        def GooseReceiver_create():
            return object()

        @staticmethod
        def GooseReceiver_setInterfaceId(_receiver, _interface):
            pass

        @staticmethod
        def GooseSubscriber_create(go_cb_ref, data_set_ref):
            return {"go_cb_ref": go_cb_ref, "data_set_ref": data_set_ref}

        @staticmethod
        def GooseSubscriber_setAppId(_subscriber, _app_id):
            pass

        @staticmethod
        def GooseSubscriber_setDstMac(_subscriber, _dst_mac):
            pass

        @staticmethod
        def GooseSubscriber_setListener(_subscriber, _callback, _parameter):
            pass

        @staticmethod
        def GooseReceiver_addSubscriber(_receiver, _subscriber):
            pass

        @staticmethod
        def GooseReceiver_start(_receiver):
            pass

        @staticmethod
        def GooseReceiver_stop(_receiver):
            pass

        @staticmethod
        def GooseReceiver_destroy(_receiver):
            pass

    monkeypatch.setattr(subscriber_module, "HAS_IEC61850", True)
    monkeypatch.setattr(subscriber_module, "iec61850", FakeIec61850, raising=False)
    monkeypatch.setattr(subscriber_module.platform, "system", lambda: "Darwin")

    receiver = subscriber_module.GooseReceiver(ReceiverConfig(interface="eth-test"))
    receiver.add_subscription("LD0/LLN0$GO$gcb1", app_id=1)
    receiver.add_subscription("LD0/LLN0$GO$disabled", app_id=2, enabled=False)

    assert receiver.start() is True
    assert len(receiver._subscriber_handles) == 1

    receiver.stop()
    assert receiver._subscriber_handles == []


def test_goose_subscription_history_tracks_dataset_changes(monkeypatch):
    from src.proto.iec61850.plugins.goose import subscriber as subscriber_module

    class FakeIec61850:
        MMS_BOOLEAN = 2

        @staticmethod
        def GooseSubscriber_getGoCbRef(subscriber):
            return subscriber["go_cb_ref"]

        @staticmethod
        def GooseSubscriber_getGoId(_subscriber):
            return "trip"

        @staticmethod
        def GooseSubscriber_getDataSet(_subscriber):
            return "LD0/LLN0$dsTrip"

        @staticmethod
        def GooseSubscriber_getConfRev(_subscriber):
            return 1

        @staticmethod
        def GooseSubscriber_getStNum(subscriber):
            return subscriber["st_num"]

        @staticmethod
        def GooseSubscriber_getSqNum(subscriber):
            return subscriber["sq_num"]

        @staticmethod
        def GooseSubscriber_getTimeAllowedToLive(_subscriber):
            return 1000

        @staticmethod
        def GooseSubscriber_getTimestamp(_subscriber):
            return 123

        @staticmethod
        def GooseSubscriber_isValid(_subscriber):
            return True

        @staticmethod
        def GooseSubscriber_getDataSetValues(subscriber):
            return subscriber["values"]

        @staticmethod
        def MmsValue_getArraySize(values):
            return len(values)

        @staticmethod
        def MmsValue_getElement(values, index):
            return values[index]

        @staticmethod
        def MmsValue_getType(_element):
            return FakeIec61850.MMS_BOOLEAN

        @staticmethod
        def MmsValue_getBoolean(element):
            return element["value"]

    monkeypatch.setattr(subscriber_module, "HAS_IEC61850", True)
    monkeypatch.setattr(subscriber_module, "iec61850", FakeIec61850, raising=False)
    receiver = subscriber_module.GooseReceiver(ReceiverConfig(interface="eth-test"))
    receiver.add_subscription(
        "LD0/LLN0$GO$gcb1",
        dataset_entries=[{"name": "LD0/XCBR1.Pos.stVal", "fc": "ST"}],
    )

    receiver._on_goose_message(
        {"go_cb_ref": "LD0/LLN0$GO$gcb1", "st_num": 1, "sq_num": 0, "values": [{"value": False}]}
    )
    receiver._on_goose_message({"go_cb_ref": "LD0/LLN0$GO$gcb1", "st_num": 2, "sq_num": 0, "values": [{"value": True}]})
    receiver._on_goose_message({"go_cb_ref": "LD0/LLN0$GO$gcb1", "st_num": 2, "sq_num": 1, "values": [{"value": True}]})

    latest = receiver.get_subscription("LD0/LLN0$GO$gcb1")
    history = receiver.get_history("LD0/LLN0$GO$gcb1")
    assert latest["message_count"] == 3
    assert latest["data_values"][0]["name"] == "LD0/XCBR1.Pos.stVal"
    assert latest["data_values"][0]["previous_value"] is False
    assert latest["data_values"][0]["changed"] is False
    assert len(history) == 3
    assert history[0]["changed_count"] == 0
    assert history[1]["changed_count"] == 1
    assert history[2]["data_values"][0]["last_update"] == history[2]["received_at"]
    assert history[1]["data_values"][0]["last_update"] == history[1]["received_at"]
    assert latest["data_values"][0]["last_update"] == history[1]["received_at"]


def test_captured_data_update_times_survive_retransmissions():
    from src.proto.iec61850.plugins.goose.subscriber import GooseReceiver

    ref = "LD0/LLN0$GO$gcb1"
    receiver = GooseReceiver(ReceiverConfig(interface="eth-test"))
    receiver.add_subscription(ref)
    for st_num, sq_num, timestamp, values in [
        (1, 0, 1000.123, (False, 1)),
        (2, 0, 2000.456, (True, 1)),
        (2, 1, 3000.789, (True, 1)),
    ]:
        receiver._on_captured_packet(
            CapturedPacket(
                timestamp=timestamp,
                src_mac="02:03:04:05:06:07",
                dst_mac="01:0C:CD:01:00:01",
                raw_bytes=b"",
                length=0,
                go_cb_ref=ref,
                st_num=st_num,
                sq_num=sq_num,
                data_values=tuple({"type": type(value).__name__, "value": value} for value in values),
            )
        )

    latest = receiver.get_subscription(ref)
    assert latest["last_update"] == 3000.789
    assert [item["last_update"] for item in latest["data_values"]] == [2000.456, 1000.123]
    history = receiver.get_history(ref)
    assert [item["last_update"] for item in history[2]["data_values"]] == [1000.123, 1000.123]
    assert [item["last_update"] for item in history[1]["data_values"]] == [2000.456, 1000.123]


@pytest.mark.parametrize("restart_st_num", [1, 10])
def test_subscription_ignores_late_frames_and_recovers_after_publisher_restart(restart_st_num):
    from src.proto.iec61850.plugins.goose.subscriber import GooseReceiver

    ref = "LD0/LLN0$GO$gcb1"
    receiver = GooseReceiver(ReceiverConfig(interface="eth-test"))
    receiver.add_subscription(ref)
    first = CapturedPacket(
        timestamp=1000.1,
        src_mac="",
        dst_mac="",
        raw_bytes=b"",
        length=0,
        go_cb_ref=ref,
        st_num=9,
        sq_num=2,
        send_timestamp=1000,
        time_allowed_to_live=1000,
        data_values=({"value": False},),
    )
    current = replace(first, timestamp=1001.1, st_num=10, sq_num=5, send_timestamp=1001, data_values=({"value": True},))
    receiver._on_captured_packet(first)
    receiver._on_captured_packet(current)
    before = receiver.get_subscription(ref)

    receiver._on_captured_packet(replace(first, timestamp=1001.2, sq_num=3))
    receiver._on_captured_packet(replace(current, timestamp=1001.3, sq_num=4))
    receiver._on_captured_packet(replace(current, timestamp=1001.4))
    assert receiver.get_subscription(ref) == before
    assert len(receiver.get_history(ref)) == 2

    receiver._on_captured_packet(replace(first, timestamp=1002.1, st_num=restart_st_num, sq_num=1, send_timestamp=1002))
    latest = receiver.get_subscription(ref)
    assert latest["st_num"] == restart_st_num
    assert latest["sq_num"] == 1
    assert latest["data_values"][0]["value"] is False
    assert latest["last_update"] == 1002.1


def test_subscription_accepts_sequence_and_state_counter_wrap():
    from src.proto.iec61850.plugins.goose.subscriber import GooseReceiver
    from src.proto.iec61850.plugins.goose.types import MAX_GOOSE_SEQUENCE

    ref = "LD0/LLN0$GO$gcb1"
    receiver = GooseReceiver(ReceiverConfig(interface="eth-test"))
    receiver.add_subscription(ref)
    packet = CapturedPacket(
        timestamp=1000,
        src_mac="",
        dst_mac="",
        raw_bytes=b"",
        length=0,
        go_cb_ref=ref,
        send_timestamp=999,
        st_num=MAX_GOOSE_SEQUENCE,
        sq_num=MAX_GOOSE_SEQUENCE,
    )
    receiver._on_captured_packet(packet)
    receiver._on_captured_packet(replace(packet, sq_num=1))
    assert receiver.get_subscription(ref)["sq_num"] == 1
    receiver._on_captured_packet(replace(packet, st_num=1, sq_num=0))
    assert receiver.get_subscription(ref)["st_num"] == 1


def test_subscription_detects_small_float_changes():
    from src.proto.iec61850.plugins.goose.publisher import GoosePublisher
    from src.proto.iec61850.plugins.goose.subscriber import GooseReceiver
    from src.proto.iec61850.plugins.goose.types import GooseDataSetEntry, IecDataType, PublisherConfig

    ref = "LD0/LLN0$GO$gcb1"
    receiver = GooseReceiver(ReceiverConfig(interface="eth-test"))
    receiver.add_subscription(ref)
    capture = GooseCaptureEngine(interface="eth-test")
    capture.set_callback(receiver._on_captured_packet)
    publisher = GoosePublisher(PublisherConfig(go_cb_ref=ref))
    publisher.add_entry(GooseDataSetEntry("mag", 1e-7, IecDataType.FLOAT))
    ethernet = bytes.fromhex("010ccd010001 020304050607 88b8")
    capture._process_packet(ethernet + publisher._build_goose_payload())
    assert publisher.update_entry(0, 2e-7)
    capture._process_packet(ethernet + publisher._build_goose_payload())

    latest = receiver.get_history(ref)[0]
    assert latest["changed_count"] == 1
    value = latest["data_values"][0]
    assert value["previous_value"] == pytest.approx(1e-7)
    assert value["value"] == pytest.approx(2e-7)
    assert value["last_update"] == latest["received_at"]


def test_subscription_tal_uses_monotonic_deadline(monkeypatch):
    from src.proto.iec61850.plugins.goose import subscriber as subscriber_module

    clock = [20.0]
    monkeypatch.setattr(subscriber_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    ref = "LD0/LLN0$GO$gcb1"
    receiver = subscriber_module.GooseReceiver(ReceiverConfig(interface="eth-test"))
    sub = receiver.add_subscription(ref)
    receiver._on_captured_packet(
        CapturedPacket(
            timestamp=1000,
            src_mac="",
            dst_mac="",
            raw_bytes=b"",
            length=0,
            go_cb_ref=ref,
            st_num=1,
            time_allowed_to_live=100,
        )
    )
    receiver._is_running = True

    def wait(timeout):
        if timeout is None:
            assert sub.state == "lost"
            receiver._is_running = False
        else:
            assert sub.state == "connected"
            assert timeout == pytest.approx(0.1)
            clock[0] += timeout

    monkeypatch.setattr(receiver._monitor_condition, "wait", wait)
    receiver._monitor_loop()
    assert sub.expires_at is None
