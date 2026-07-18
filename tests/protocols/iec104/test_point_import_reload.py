"""IEC104 Excel 点表导入后的运行时同步回归测试。"""

import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from src.enums.modbus_def import ProtocolType
from src.web.api.channel.import_points import import_points
from src.web.api.exceptions import OperationError


class _UploadFile:
    filename = "points.xlsx"

    async def read(self) -> bytes:
        return b"xlsx"


class Iec104PointImportReloadTests(unittest.TestCase):
    def _import(self, protocol_type: ProtocolType, was_running: bool, *, start_success: bool = True):
        device = Mock()
        device.protocol_type = protocol_type
        device.name = "IEC104"
        device.is_protocol_running.return_value = was_running
        device.is_auto_read_running.return_value = False

        controller = Mock()
        controller.get_device_by_id.return_value = device
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(device_controller=controller)))

        reload_mock = AsyncMock()
        new_device = Mock()
        new_device.start = AsyncMock(return_value=start_success)
        reload_mock.return_value = new_device
        with (
            patch("src.web.api.channel.import_points.require_tabular_point_channel"),
            patch("src.web.api.channel.import_points.get_storage_path", return_value=None),
            patch("src.data.dao.point_dao.PointDao.delete_points_by_channel", return_value=0),
            patch("src.web.api.channel.import_points.ExcelPointImporter") as importer_class,
            patch("src.web.api.channel.import_points.reload_device_instance", reload_mock),
        ):
            importer_class.return_value.import_from_excel.return_value = (1, 2, 3, 4)
            response = asyncio.run(import_points(request, channel_id=7, file=_UploadFile()))

        return response, device, controller, reload_mock, new_device

    def test_running_iec104_server_is_rebuilt_and_restarted(self):
        response, device, controller, reload_mock, new_device = self._import(ProtocolType.Iec104Server, True)

        reload_mock.assert_awaited_once_with(controller, 7, is_start=False)
        new_device.start.assert_awaited_once_with()
        device.importDataPointFromChannel.assert_not_called()
        self.assertEqual(response.data["total"], 10)

    def test_stopped_iec104_client_is_rebuilt_without_starting(self):
        _response, device, controller, reload_mock, new_device = self._import(ProtocolType.Iec104Client, False)

        reload_mock.assert_awaited_once_with(controller, 7, is_start=False)
        new_device.start.assert_not_awaited()
        device.importDataPointFromChannel.assert_not_called()

    def test_restart_failure_is_reported_instead_of_returning_success(self):
        with self.assertRaisesRegex(OperationError, "运行时模型同步失败"):
            self._import(ProtocolType.Iec104Server, True, start_success=False)


if __name__ == "__main__":
    unittest.main()
