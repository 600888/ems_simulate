import time

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
            _tlv(0x84, b"\x01"),
            _tlv(0x85, b"\x02"),
            _tlv(0x86, b"\x01"),
            _tlv(0x87, b"\x01"),
            _tlv(0x88, b"\x00"),
            _tlv(0x89, b"\x01"),
            _tlv(0x8A, _tlv(0x09, b"\x01")),
        ]
    )
    pdu = _tlv(0xA1, pdu_fields)
    ethernet = bytes.fromhex("010ccd010001 020304050607 88b8")
    goose_header = bytes.fromhex("0001 0000 0000 0000")
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
    assert packets[0]["data_values"] == [{"type": "boolean", "value": True}]


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

    receiver = subscriber_module.GooseReceiver(ReceiverConfig(interface="eth-test"))
    receiver.add_subscription("LD0/LLN0$GO$gcb1", app_id=1)

    assert receiver.start() is True
    assert len(receiver._subscriber_handles) == 1

    receiver.stop()
    assert receiver._subscriber_handles == []
