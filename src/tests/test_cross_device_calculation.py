import sys
import os
import time
import unittest
import json
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from src.device.core.point.point_manager import PointManager
from src.device.core.point.point_calculator import PointCalculator
import logging
logging.basicConfig(
    level=logging.DEBUG, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("test.log", encoding='utf-8', mode='w'),
        logging.StreamHandler()
    ]
)

# Mock Device class
class MockDevice:
    def __init__(self, name):
        self.name = name
        self.point_manager = PointManager()

class TestCrossDeviceCalculation(unittest.TestCase):
    def setUp(self):
        # Create devices
        self.dev_a = MockDevice("DeviceA")
        self.dev_b = MockDevice("DeviceB")
        
        # Mock DeviceController
        self.mock_dc = MagicMock()
        self.mock_dc.device_map = {
            "DeviceA": self.dev_a,
            "DeviceB": self.dev_b
        }
        
        # Patch where it is imported in PointCalculator methods
        self.dc_patcher = patch('src.device_controller.device_controller', self.mock_dc)
        self.dc_patcher.start()

        # Mock PointMappingService
        self.mock_service_patcher = patch('src.device.core.point.point_calculator.PointMappingService')
        self.mock_service = self.mock_service_patcher.start()

        # Initialize Calculator for Device A (Target Device)
        self.calculator = PointCalculator(self.dev_a)

    def tearDown(self):
        self.dc_patcher.stop()
        self.mock_service_patcher.stop()
        self.calculator.stop()

    def create_point(self, device, code, value=0.0):
        point = Yc()
        point.code = code
        point.name = f"Point {code} in {device.name}"
        point.value = int(value)
        # Manually set real_value as PointCalculator uses it
        # In Yc (src/enums/points/yc.py), usually there's a property real_value
        # For BasePoint, we can inject it
        point.real_value = float(value)
        
        device.point_manager.code_map[code] = point
        return point

    def test_cross_device_calculation(self):
        # Scenario: DeviceA.Target = DeviceB.Source1 + DeviceA.Source2
        
        # 1. Setup points
        # Source in Device B
        p_b_1 = self.create_point(self.dev_b, "P_B_1", 10.0)
        # Source in Device A
        p_a_2 = self.create_point(self.dev_a, "P_A_2", 20.0)
        # Target in Device A
        p_target = self.create_point(self.dev_a, "TARGET", 0.0)

        # 2. Setup mapping
        source_points = [
            {"device_name": "DeviceB", "point_code": "P_B_1", "alias": "val_b"},
            {"device_name": "DeviceA", "point_code": "P_A_2", "alias": "val_a"}
        ]
        
        mapping = {
            "id": 1,
            "device_name": "DeviceA",
            "target_point_code": "TARGET",
            "source_point_codes": json.dumps(source_points),
            "formula": "val_a + val_b",
            "enable": True
        }
        self.mock_service.get_all_mappings.return_value = [mapping]

        # 3. Start calculator
        print("Starting calculator...")
        self.calculator.start()

        # 4. Trigger change
        # Simulate change in Device B point
        print("Triggering change in DeviceB.P_B_1...")
        self.calculator.on_source_changed(p_b_1)
        
        # Wait for thread
        time.sleep(0.1)

        # 5. Verify result
        # Should be 20 + 10 = 30
        print(f"Target value: {p_target.value}")
        # Note: PointCalculator sets real_value and value (int)
        # We checked code: if set_real_value exists calls it, else sets value=int(result)
        # Yc likely has both.
        # Let's check both or real_value if present
        result_val = getattr(p_target, 'real_value', p_target.value)
        self.assertEqual(float(result_val), 30.0, f"Expected 30.0, got {result_val}")

        # 6. Test change in Device A source point
        print("Triggering change in DeviceA.P_A_2...")
        # Update point value
        p_a_2.real_value = 50.0
        self.calculator.on_source_changed(p_a_2)
        
        time.sleep(0.1)
        
        # Should be 50 + 10 = 60
        result_val = getattr(p_target, 'real_value', p_target.value)
        self.assertEqual(float(result_val), 60.0, f"Expected 60.0, got {result_val}")

if __name__ == '__main__':
    unittest.main()
