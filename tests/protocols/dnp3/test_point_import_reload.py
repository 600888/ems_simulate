"""DNP3 Excel 点表导入后的运行时同步回归测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.enums.modbus_def import ProtocolType
from src.web.api.channel.import_points import _sync_imported_points


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol_type", [ProtocolType.Dnp3Server, ProtocolType.Dnp3Client])
@pytest.mark.parametrize("was_running", [False, True])
async def test_dnp3_import_rebuilds_protocol_point_database(protocol_type, was_running):
    device = Mock()
    device.protocol_type = protocol_type
    device.is_protocol_running.return_value = was_running

    controller = Mock()
    controller.get_device_by_id.return_value = device
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(device_controller=controller)))

    with patch(
        "src.web.api.channel.import_points.reload_device_instance",
        new_callable=AsyncMock,
    ) as reload_mock:
        await _sync_imported_points(request, 67)

    reload_mock.assert_awaited_once_with(controller, 67, is_start=was_running)
    device.importDataPointFromChannel.assert_not_called()
