import asyncio
import unittest
from unittest.mock import MagicMock, patch

from src.data.service.point_tree_service import PointTreeService
from src.device.core.point.point_manager import PointManager
from src.enums.modbus_def import ProtocolType
from src.enums.points.yc import Yc
from src.enums.points.yx import Yx


class MockDevice:
    def __init__(self, name, device_id, protocol_type=ProtocolType.ModbusTcp):
        self.name = name
        self.device_id = device_id
        self.protocol_type = protocol_type
        self.point_manager = PointManager()
        self.yc_dict = {}
        self.yx_dict = {}
        # yt/yk are in point_manager


class TestPointTree(unittest.IsolatedAsyncioTestCase):
    async def test_get_tree(self):
        # 1. Setup Mock Devices and Points
        dev1 = MockDevice("Device A", 1)

        # Add YC points
        yc1 = Yc()
        yc1.code = "YC001"
        yc1.name = "Voltage"
        yc1.value = 220
        yc1.real_value = 220.5
        yc1.rtu_addr = 1
        yc1.hex_address = "0x0064"

        dev1.yc_dict = {1: [yc1]}

        # Add YX points
        yx1 = Yx()
        yx1.code = "YX001"
        yx1.name = "Switch"
        yx1.value = 1
        yx1.rtu_addr = 1
        yx1.hex_address = "0x00C8"

        dev1.yx_dict = {1: [yx1]}

        # Mock DeviceController
        mock_dc = MagicMock()
        mock_dc.device_list = [dev1]

        # Patch get_device_controller
        with patch("src.data.service.point_tree_service.get_device_controller", new_callable=MagicMock) as mock_get_dc:
            # Configure the mock to return a future that resolves to mock_dc
            f = asyncio.Future()
            f.set_result(mock_dc)
            mock_get_dc.return_value = f

            # 2. Call Service
            tree = await PointTreeService.get_tree()

            # 3. Verify Structure
            self.assertEqual(len(tree), 1)
            device_node = tree[0]
            self.assertEqual(device_node.label, "Device A")

            # Check Children (Types)
            # Should have YC and YX
            self.assertEqual(len(device_node.children), 2)

            yc_node = next((n for n in device_node.children if n.label == "遥测"), None)
            self.assertIsNotNone(yc_node)
            self.assertEqual(len(yc_node.children), 1)
            self.assertEqual(yc_node.children[0].code, "YC001")
            self.assertEqual(yc_node.children[0].value, 220.5)

            yx_node = next((n for n in device_node.children if n.label == "遥信"), None)
            self.assertIsNotNone(yx_node)
            self.assertEqual(len(yx_node.children), 1)
            self.assertEqual(yx_node.children[0].code, "YX001")

    async def test_iec61850_tree_uses_data_model_ld_ln_hierarchy(self):
        device = MockDevice("IED", 2, ProtocolType.Iec61850Server)
        power = Yc(
            code="power",
            name="有功功率",
            address="IEDLD0/MMXU1.TotW.mag.f",
            value=10,
        )
        position = Yx(
            code="position",
            name="开关位置",
            address="IEDLD0/XCBR1.Pos.stVal",
            value=1,
        )
        alarm = Yx(
            code="alarm",
            name="告警",
            address="IEDLD1/GGIO1.Alm.stVal",
            value=0,
        )
        device.yc_dict = {1: [power]}
        device.yx_dict = {1: [position, alarm]}

        mock_dc = MagicMock(device_list=[device])
        with patch("src.data.service.point_tree_service.get_device_controller", new_callable=MagicMock) as mock_get_dc:
            future = asyncio.Future()
            future.set_result(mock_dc)
            mock_get_dc.return_value = future

            tree = await PointTreeService.get_tree("IED")

        self.assertEqual([node.label for node in tree[0].children], ["IEDLD0", "IEDLD1"])
        ld0 = tree[0].children[0]
        self.assertIsNone(ld0.frame_type)
        self.assertEqual([node.label for node in ld0.children], ["MMXU1", "XCBR1"])
        self.assertEqual(ld0.children[0].children[0].code, "power")
        self.assertEqual(ld0.children[1].children[0].type, "YX")


if __name__ == "__main__":
    unittest.main()
