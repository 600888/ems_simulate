import socket
import threading
import time
from unittest.mock import Mock

import pytest

from src.proto.iec61850.plugins.goose import capture as capture_module
from src.proto.iec61850.plugins.goose.capture import GooseCaptureEngine
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
            return subscriber_module.MmsType.BOOLEAN

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
