import pytest

from src.data.service.channel_service import ChannelService
from src.device.protocol.iec101_handler import IEC101ClientHandler
from src.device.protocol.runtime_config import get_protocol_param_defaults, normalize_protocol_params
from src.enums.modbus_def import ProtocolType
from src.enums.points.yc import Yc
from src.proto.iec60870.asdu import ASDU, InformationObject


def test_channel_mapping_exposes_iec101_master_and_slave():
    assert ChannelService.get_protocol_type({"protocol_type": 6, "conn_type": 0}) is ProtocolType.Iec101Client
    assert ChannelService.get_protocol_type({"protocol_type": 6, "conn_type": 3}) is ProtocolType.Iec101Server


def test_iec101_runtime_defaults_and_address_width_validation():
    client = get_protocol_param_defaults(6, 0)
    assert client["link_mode"] == "unbalanced"
    assert client["link_address_size"] == 1
    assert client["common_address_size"] == 2
    assert client["io_address_size"] == 3
    assert client["general_interrogation_on_connect"] is True

    normalized = normalize_protocol_params(6, 0, {"link_mode": "BALANCED", "io_address_size": 2})
    assert normalized["link_mode"] == "balanced"
    assert normalized["io_address_size"] == 2

    with pytest.raises(ValueError, match="链路地址"):
        normalize_protocol_params(6, 0, {"link_address_size": 1, "link_address": 256})


def test_iec101_client_received_asdu_marks_ui_point_valid():
    handler = IEC101ClientHandler()
    point = Yc(
        rtu_addr="1",
        address="0x0064",
        code="voltage",
        value=0,
        iec_type_id="M_ME_NC_1",
        decode="0x42",
    )
    handler.add_points([point])

    handler._on_asdu(ASDU(13, 20, 1, [InformationObject(100, 12.5, quality=0x10)]))

    assert point.value == pytest.approx(12.5)
    assert point.real_value == pytest.approx(12.5)
    assert point.is_valid is True
    assert point.iec_quality_value == 0x10
