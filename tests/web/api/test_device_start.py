from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.enums.modbus_def import ProtocolType
from src.web.api.channel.device_manage import create_and_start_device
from src.web.api.schemas import ChannelIdRequest


@pytest.mark.asyncio
async def test_starting_client_connects_without_enabling_default_auto_read():
    channel = {
        "id": 7,
        "code": "CLIENT-1",
        "name": "客户端设备",
        "protocol_type": 1,
        "conn_type": 1,
        "ip": "127.0.0.1",
        "port": 502,
    }
    device = SimpleNamespace(
        name="",
        start=AsyncMock(return_value=True),
        start_auto_read=AsyncMock(),
        set_device_provider=Mock(),
    )
    builder = Mock()
    builder.makeGeneralDevice.return_value = device
    controller = SimpleNamespace(device_list=[], device_map={})
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(device_controller=controller)),
    )

    with (
        patch(
            "src.web.api.channel.device_manage.ChannelService.get_channel_by_id",
            return_value=channel,
        ),
        patch(
            "src.web.api.channel.device_manage.ChannelService.get_protocol_type",
            return_value=ProtocolType.ModbusTcpClient,
        ),
        patch("src.web.api.channel.device_manage.get_device_builder", return_value=builder),
        patch("src.web.api.channel.device_manage.configure_builder_network"),
        patch(
            "src.web.api.channel.device_manage.PointMappingService.get_all_mappings",
            return_value=[],
        ),
    ):
        response = await create_and_start_device(ChannelIdRequest(channel_id=7), request)

    device.start.assert_awaited_once_with()
    device.start_auto_read.assert_not_awaited()
    assert controller.device_map["客户端设备"] is device
    assert response.data == {"device_name": "客户端设备"}


@pytest.mark.asyncio
async def test_starting_dnp3_server_starts_listening():
    channel = {
        "id": 56,
        "code": "DNP3-SERVER",
        "name": "DNP3服务端",
        "protocol_type": 5,
        "conn_type": 2,
        "ip": "0.0.0.0",
        "port": 20000,
    }
    device = SimpleNamespace(
        name="",
        start=AsyncMock(return_value=True),
        set_device_provider=Mock(),
    )
    builder = Mock()
    builder.makeGeneralDevice.return_value = device
    controller = SimpleNamespace(device_list=[], device_map={})
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(device_controller=controller)),
    )

    with (
        patch(
            "src.web.api.channel.device_manage.ChannelService.get_channel_by_id",
            return_value=channel,
        ),
        patch(
            "src.web.api.channel.device_manage.ChannelService.get_protocol_type",
            return_value=ProtocolType.Dnp3Server,
        ),
        patch("src.web.api.channel.device_manage.get_device_builder", return_value=builder),
        patch("src.web.api.channel.device_manage.configure_builder_network"),
        patch(
            "src.web.api.channel.device_manage.PointMappingService.get_all_mappings",
            return_value=[],
        ),
    ):
        response = await create_and_start_device(ChannelIdRequest(channel_id=56), request)

    device.start.assert_awaited_once_with()
    assert controller.device_map["DNP3服务端"] is device
    assert response.data == {"device_name": "DNP3服务端"}
