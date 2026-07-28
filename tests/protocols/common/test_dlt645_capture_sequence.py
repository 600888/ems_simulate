from types import SimpleNamespace

import pytest

from src.device.protocol.dlt645_handler import DLT645ClientHandler, DLT645ServerHandler


class _CaptureService:
    def __init__(self, messages):
        self.messages = messages
        self.cleared = False

    def get_captured_messages(self, count):
        assert count == 0
        return self.messages

    def clear_captured_messages(self):
        self.messages = []
        self.cleared = True


def _record(record_id: str, timestamp: float):
    return SimpleNamespace(
        to_dict=lambda: {
            "id": record_id,
            "direction": "RX",
            "data": "68",
            "hex_string": "68",
            "timestamp": timestamp,
            "time": f"t{timestamp}",
        }
    )


@pytest.mark.parametrize(
    ("handler_type", "service_attribute"),
    [
        (DLT645ServerHandler, "_server"),
        (DLT645ClientHandler, "_client"),
    ],
)
def test_dlt645_capture_adds_stable_positive_sequence_ids(handler_type, service_attribute):
    first = _record("first", 1.0)
    second = _record("second", 2.0)
    third = _record("third", 3.0)
    service = _CaptureService([first, second])
    handler = handler_type()
    setattr(handler, service_attribute, service)

    initial = handler.get_captured_messages()
    service.messages = [first, second, third]
    refreshed = handler.get_captured_messages(count=2)

    assert [item["sequence_id"] for item in initial] == [1, 2]
    assert [item["sequence_id"] for item in refreshed] == [2, 3]
    assert all(item["sequence_id"] >= 1 for item in refreshed)


def test_dlt645_capture_sequence_resets_when_messages_are_cleared():
    service = _CaptureService([_record("before-clear", 1.0)])
    handler = DLT645ServerHandler()
    handler._server = service

    assert handler.get_captured_messages()[0]["sequence_id"] == 1

    handler.clear_captured_messages()
    service.messages = [_record("after-clear", 2.0)]

    assert service.cleared is True
    assert handler.get_captured_messages()[0]["sequence_id"] == 1
