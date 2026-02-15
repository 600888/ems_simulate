import sys
import os
import unittest
import asyncio
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from src.data.service.point_tree_service import PointTreeService
from src.device.core.point.point_manager import PointManager
from src.enums.points.yc import Yc
from src.enums.points.yx import Yx

class MockDevice:
    def __init__(self, name, device_id):
        self.name = name
        self.device_id = device_id
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
        with patch('src.data.service.point_tree_service.get_device_controller', new_callable=MagicMock) as mock_get_dc:
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

if __name__ == '__main__':
    unittest.main()
