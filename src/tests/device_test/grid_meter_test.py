import unittest

from src.config.global_config import CSV_DIR
from src.device.grid_meter import GridMeter
from src.device.factory.grid_meter_build import GridMeterBuilder


class GridMeterTestCase(unittest.TestCase):
    def testImportPlanJson(self) -> None:
        csv_file_path = CSV_DIR + "tuobang_gridMeter.csv"
        grid_meter_builder = GridMeterBuilder()
        grid_meter = grid_meter_builder.makeGridMeter(1, csv_file_path, "tcp", True)
        print(grid_meter.port)
        print(grid_meter.isSimulationRunning())

        # grid_meter_meter.plan.clearAllPlan()
        # grid_meter_meter.plan.importAllPlan()
        # grid_meter_meter.plan.current_plan_name = "output.json"
        # grid_meter_meter.plan.start()
