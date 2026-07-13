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
            _tlv(0x84, b"\x00" * 8),
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
    assert packets[0]["data_values"][0]["type"] == "boolean"
    assert packets[0]["data_values"][0]["value"] is True
    assert packets[0]["data_values"][0]["offset"] > 0
    assert packets[0]["fields"]


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
    monkeypatch.setattr(subscriber_module.platform, "system", lambda: "Linux")

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
