import unittest

from src.config.global_config import CSV_DIR
from src.device.device import Device


class DeviceTestCase(unittest.TestCase):
    def importDataPointCsv(self):
        self.device = Device()
        self.device.importDataPointFromCsv(CSV_DIR + "bms1_modbus_tcp.csv")
        self.device.initModbusTcpServer(502)
        self.device.server.start()

    def test_showDataPointInCmd(self):
        self.importDataPointCsv()
        self.device.showDataPointInCmd(1)

    def test_getTableData(self):
        self.importDataPointCsv()
        self.device.get_table_data(1, "")

    def testImportAllJsonPlan(self):
        self.device = Device()
        self.device.importDataPointFromCsv(CSV_DIR + "tuobang_pcs.csv")
        self.device.initPlan()
        self.device.plan.importAllPlanJson()
