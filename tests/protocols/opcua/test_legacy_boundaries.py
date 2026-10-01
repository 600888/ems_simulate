"""UA points must never enter numeric legacy point mutations."""

from types import SimpleNamespace

import pytest

from src.enums.modbus_def import ProtocolType
from src.web.api.channel.protocol_guards import require_tabular_point_channel
from src.web.api.exceptions import ValidationError
from src.web.api.point.router import _get_device


def test_legacy_excel_import_rejects_opcua(monkeypatch):
    monkeypatch.setattr(
        "src.web.api.channel.protocol_guards.ChannelService.get_channel_by_id",
        lambda _channel_id: {"id": 1, "protocol_type": 7},
    )
    with pytest.raises(ValidationError, match="专属"):
        require_tabular_point_channel(1)


@pytest.mark.parametrize("role", [ProtocolType.OpcUaClient, ProtocolType.OpcUaServer])
def test_legacy_point_endpoints_reject_opcua(role):
    device = SimpleNamespace(protocol_type=role)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                device_controller=SimpleNamespace(device_map={"UA": device}),
            )
        )
    )
    with pytest.raises(ValidationError, match="专属"):
        _get_device("UA", request)
