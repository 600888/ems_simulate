"""Regression tests for IEC 61850 facade-to-handler delegation."""

import unittest
from unittest.mock import Mock

from src.device.core.device import Device
from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yc, Yx


class IEC61850DeviceFacadeTests(unittest.TestCase):
    def test_remote_discovery_delegates_to_client_handler(self):
        device = Device(ProtocolType.Iec61850Client)
        handler = IEC61850ClientHandler()
        handler.remote_discover_model = Mock(return_value=True)
        device.protocol_handler = handler

        self.assertTrue(device.iec61850_remote_discover_model())
        handler.remote_discover_model.assert_called_once_with()

    def test_client_model_load_delegates_to_client_handler(self):
        device = Device(ProtocolType.Iec61850Client)
        handler = IEC61850ClientHandler()
        handler.load_model_from_icd = Mock(return_value=True)
        device.protocol_handler = handler

        self.assertTrue(device.load_iec61850_model("client.icd"))
        handler.load_model_from_icd.assert_called_once_with("client.icd")

    def test_server_model_load_delegates_to_server_handler(self):
        device = Device(ProtocolType.Iec61850Server)
        handler = IEC61850ServerHandler()
        handler.load_model = Mock(return_value=True)
        device.protocol_handler = handler

        self.assertTrue(device.load_iec61850_model("server.icd"))
        handler.load_model.assert_called_once_with("server.icd")

    def test_discovered_points_are_loaded_into_memory_table(self):
        device = Device(ProtocolType.Iec61850Client)

        device._on_iec61850_points_discovered(
            [
                {
                    "address": "IED1LD0/MMXU1.TotW.mag.f",
                    "frame_type": 0,
                    "ref": "IED1LD0/MMXU1.TotW.mag.f",
                    "code": "MMXU1.TotW.mag.f",
                    "name": "总有功功率",
                    "fc": "MX",
                },
                {
                    "address": "IED1LD0/GGIO1.Alm.stVal",
                    "frame_type": 1,
                    "ref": "IED1LD0/GGIO1.Alm.stVal",
                    "code": "GGIO1.Alm.stVal",
                    "name": "告警",
                    "fc": "ST",
                },
            ]
        )

        self.assertEqual(device.slave_id_list, [1])
        yc_points, yx_points, _, _ = device.point_manager.get_points_by_slave(1)
        self.assertEqual(len(yc_points), 1)
        self.assertEqual(len(yx_points), 1)
        self.assertIsInstance(yc_points[0], Yc)
        self.assertIsInstance(yx_points[0], Yx)
        self.assertEqual(yc_points[0].address, "IED1LD0/MMXU1.TotW.mag.f")


if __name__ == "__main__":
    unittest.main()
