import sys
import os
import time
import unittest
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from src.device.core.point.point_manager import PointManager
from src.device.core.point.point_calculator import PointCalculator
from src.enums.points.yc import Yc
from src.enums.point_data import BasePoint

class TestPointCalculator(unittest.TestCase):
    def setUp(self):
        self.pm = PointManager()
        self.calculator = PointCalculator(self.pm)
        
        # Mock PointMappingService
        self.mock_service_patcher = patch('src.device.core.point.point_calculator.PointMappingService')
        self.mock_service = self.mock_service_patcher.start()
        
    def tearDown(self):
        self.mock_service_patcher.stop()

    def create_point(self, code, value=0.0):
        point = Yc()
        point.code = code
        point.name = f"Point {code}"
        point.value = int(value) # Yc value is int usually? BasePoint has value
        # Make sure real_value is set if used
        # Check Yc implementation: value setter updates real_value? 
        # In this mock env, we might need to be careful.
        # Let's assume point.value updates triggers
        # But PointCalculator uses real_value if available.
        # Let's manually set it to be safe for this test
        point._real_value = float(value) 
        
        self.pm.code_map[code] = point
        return point

    def test_simple_addition(self):
        # Setup points
        p1 = self.create_point("P1", 10)
        p2 = self.create_point("P2", 20)
        target = self.create_point("TARGET", 0)

        # Setup mapping
        mapping = {
            "id": 1,
            "target_point_code": "TARGET",
            "source_point_codes": '["P1", "P2"]',
            "formula": "P1 + P2",
            "enable": True
        }
        self.mock_service.get_all_mappings.return_value = [mapping]

        # Start calculator
        self.calculator.start() # reloading mappings

        # Trigger update (simulate signal)
        # PointCalculator subscribes to value_changed.
        # We need to manually call on_source_changed because signals might not work in simple unittest without event loop/blinker setup if not careful.
        # But BasePoint uses blinker. Is blinker installed? Yes.
        # Let's try calling on_source_changed directly to test logic first.
        
        self.calculator.on_source_changed(p1)
        
        # Wait for thread executor
        time.sleep(0.1)
        
        # Check target value
        # TARGET should be 10 + 20 = 30
        self.assertEqual(target.real_value, 30.0)

    def test_complex_formula(self):
        p1 = self.create_point("A", 10)
        p2 = self.create_point("B", 5)
        target = self.create_point("C", 0)

        mapping = {
            "id": 2,
            "target_point_code": "C",
            "source_point_codes": '["A", "B"]',
            "formula": "(A - B) * 2",
            "enable": True
        }
        self.mock_service.get_all_mappings.return_value = [mapping]
        self.calculator.start()
        
        self.calculator.on_source_changed(p1)
        time.sleep(0.1)
        
        # (10 - 5) * 2 = 10
        self.assertEqual(target.real_value, 10.0)

    def test_bitwise_operation(self):
        p1 = self.create_point("X", 3) # 011
        p2 = self.create_point("Y", 5) # 101
        target = self.create_point("Z", 0)

        mapping = {
            "id": 3,
            "target_point_code": "Z",
            "source_point_codes": '["X", "Y"]',
            "formula": "X & Y",
            "enable": True
        }
        self.mock_service.get_all_mappings.return_value = [mapping]
        self.calculator.start()
        
        self.calculator.on_source_changed(p1)
        time.sleep(0.1)
        
        # 3 & 5 = 1
        self.assertEqual(target.real_value, 1.0)

if __name__ == '__main__':
    unittest.main()
