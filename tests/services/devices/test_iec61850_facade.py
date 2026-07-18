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
        handler.load_model_from_icd.assert_called_once_with("client.icd", scl_result=None)

    def test_server_model_load_delegates_to_server_handler(self):
        device = Device(ProtocolType.Iec61850Server)
        handler = IEC61850ServerHandler()
        handler.load_model = Mock(return_value=True)
        device.protocol_handler = handler

        self.assertTrue(device.load_iec61850_model("server.icd"))
        handler.load_model.assert_called_once_with("server.icd", scl_result=None)

    def test_server_model_load_populates_goose_discovery_cache(self):
        handler = IEC61850ServerHandler()
        handler._server = Mock()
        handler._server.load_model.return_value = True
        handler._server.get_discovered_goose_items.return_value = [
            {"go_cb_ref": "LD0/LLN0$GO$gcb1", "data_set_ref": "LD0/LLN0$ds1"}
        ]
        handler._server.browse_datasets.return_value = [{"ref": "LD0/LLN0$ds1"}]

        self.assertTrue(handler.load_model("server.icd"))
        self.assertEqual(handler._discovered_goose_items[0]["go_cb_ref"], "LD0/LLN0$GO$gcb1")
        self.assertEqual(handler._discovered_datasets, [{"ref": "LD0/LLN0$ds1"}])

    def test_failed_server_model_load_keeps_existing_discovery_cache(self):
        handler = IEC61850ServerHandler()
        handler._server = Mock()
        handler._server.load_model.return_value = False
        handler._discovered_goose_items.append({"go_cb_ref": "existing"})

        self.assertFalse(handler.load_model("broken.icd"))
        self.assertEqual(handler._discovered_goose_items, [{"go_cb_ref": "existing"}])

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
