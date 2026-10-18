"""Server addresses must survive every device construction entry point."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.device_controller import DeviceController
from src.enums.modbus_def import ProtocolType
from src.web.api.channel import helpers
from src.web.api.channel.router import create_channel
from src.web.api.schemas.channel import ChannelCreateRequest


@pytest.mark.parametrize("ip", ["192.168.12.11", "192.168.12.21", "0.0.0.0"])
@pytest.mark.parametrize("entry", ["create", "reload", "startup"])
@pytest.mark.parametrize(
    ("protocol_id", "protocol"),
    [
        (1, ProtocolType.ModbusTcpServer),
        (2, ProtocolType.Iec104Server),
        (3, ProtocolType.Dlt645Server),
        (4, ProtocolType.Iec61850Server),
        (5, ProtocolType.Dnp3Server),
        (7, ProtocolType.OpcUaServer),
        (8, ProtocolType.Dlt698Server),
    ],
)
def test_server_preserves_configured_listen_address(ip, entry, protocol_id, protocol):
    channel = dict(id=1941, code="SERVER", name="server", protocol_type=protocol_id, conn_type=2, ip=ip, port=2404)
    device = SimpleNamespace(name="server", set_device_provider=Mock())
    builder = Mock()
    builder.makeGeneralDevice.return_value = device
    controller = SimpleNamespace(device_list=[], device_map={})
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(device_controller=controller)))

    with (
        patch.object(helpers.ChannelService, "get_channel_by_code", return_value=None),
        patch.object(helpers.ChannelService, "get_all_channels", return_value=[channel] if entry == "startup" else []),
        patch.object(helpers.ChannelService, "provision_channel", return_value=(1941, 1941)),
        patch.object(helpers.ChannelService, "get_protocol_type", return_value=protocol),
        patch.object(helpers.ChannelConfigurationService, "get_protocol_params", return_value={"values": {}}),
        patch.object(helpers.ChannelConfigurationService, "get_runtime_security", return_value={}),
        patch.object(helpers.PointMappingService, "get_all_mappings", return_value=[]),
        patch("src.web.api.channel.router.OpcUaDeviceConfigurationService.prepare", return_value={}),
    ):
        if entry == "create":
            if protocol == ProtocolType.OpcUaServer:
                channel["opcua_config"] = {"mode": "Sign", "policy": "Basic256Sha256"}
            with patch("src.web.api.channel.router.get_device_builder", return_value=builder):
                asyncio.run(create_channel(ChannelCreateRequest(**channel), request))
            assert controller.device_list == [device]
        elif entry == "startup":
            with patch("src.device_controller.GeneralDeviceBuilder", return_value=builder):
                DeviceController._import_device_from_db(controller)
            assert controller.device_list == [device]
        else:
            # Restart, config reload and copy all use this shared helper.
            helpers.configure_builder_network(builder, 2, protocol, ip, 2404, channel)

    builder.setDeviceNetConfig.assert_called_once_with(port=2404, ip=ip)
