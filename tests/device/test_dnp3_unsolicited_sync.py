from src.device.protocol.dnp3_handler import DNP3ClientHandler
from src.enums.points.change_tracker import ChangeSource
from src.enums.points.yc import Yc
from src.enums.points.yx import Yx


def test_unsolicited_analog_update_syncs_protocol_cache_to_application_point():
    handler = DNP3ClientHandler()
    point = Yc(address=7, code="AI-7", value=0, mul_coe=0.1, add_coe=5)
    handler.add_points([point])

    handler._on_point_update(32, 7, 100, "unsolicited")

    assert point.value == 100.0
    assert point.real_value == 15.0
    assert point.is_valid is True
    assert point.change_history[-1].source is ChangeSource.CLIENT_READ
    assert point.change_history[-1].detail == "DNP3主动上报 AI-7"


def test_unsolicited_binary_event_group_updates_matching_binary_point_only():
    handler = DNP3ClientHandler()
    analog = Yc(address=12, code="AI-12", value=0)
    binary = Yx(address=12, code="BI-12", value=0)
    handler.add_points([analog, binary])

    handler._on_point_update(2, 12, True, "unsolicited")

    assert binary.value == 1
    assert binary.is_valid is True
    assert analog.value == 0
    assert analog.is_valid is None


def test_unconfigured_or_unsupported_dnp3_update_is_ignored():
    handler = DNP3ClientHandler()
    point = Yx(address=3, code="BI-3", value=0)
    handler.add_points([point])

    handler._on_point_update(99, 3, True, "unsolicited")
    handler._on_point_update(2, 4, True, "unsolicited")

    assert point.value == 0
    assert point.is_valid is None
