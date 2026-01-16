import unittest

from src.config.global_config import CSV_DIR
from src.device.electricity_meter import ElectricityMeter
from src.device.factory.electricity_builder import ElectricityMeterBuilder


class ElectricityMeterTestCase(unittest.TestCase):
    def testImportPlanJson(self) -> None:
        electricity_meter = ElectricityMeter()
        csv_file_path = CSV_DIR + "tuobang_energyMeter.csv"
        electricity_meter.importDataPointFromCsv(csv_file_path)
        electricity_meter.initPlan()
        electricity_meter.plan.clearAllPlan()
        electricity_meter.plan.importAllPlan()
        plan_list = list(electricity_meter.plan.is_set_plan_dict.keys())
        # table_data = electricity_meter.plan.getTableData(plan_list[0], point_name="")
        print(plan_list)
        # print(table_data)

    def testStartPlan(self) -> None:
        csv_file_path = CSV_DIR + "tuobang_energyMeter.csv"
        electricity_builder = ElectricityMeterBuilder()
        electricity_meter = electricity_builder.makeElectricityMeter(
            1, csv_file_path, "tcp", True
        )
        electricity_meter.plan.clearAllPlan()
        electricity_meter.plan.importAllPlan()
        electricity_meter.plan.current_plan_name = "output.json"
        electricity_meter.plan.start()

    def testStartPlanSimulation(self) -> None:
        electricity_meter = ElectricityMeter()
        csv_file_path = CSV_DIR + "electricity_meter.csv"
        electricity_meter.importDataPointFromCsv(csv_file_path)
        electricity_meter.setPlanPointList()
        electricity_meter.importPlanJson()
        # electricity_meter.modbus_tcp_server.startServer()
        # electricity_meter.startPlanSimulation()
