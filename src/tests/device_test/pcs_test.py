import sys
import unittest

from src.config.global_config import CSV_DIR

sys.path.append("../../../")

from src.device.types.pcs import Pcs
from src.device.factory.pcs_builder import PcsBuilder


class PcsTestCase(unittest.TestCase):
    def importDataPointCsv(self):
        pcs_builder = PcsBuilder()
        self.pcs = pcs_builder.makePcs(1, CSV_DIR + "tuobang_pcs.csv", "tcp", True)

    def testImportDataPointCsv(self):
        self.importDataPointCsv()

    def testExportPointCsv(self):
        self.importDataPointCsv()
        self.pcs.exportDataPointCsv("../point_csv/test.csv")

    def test_showDataPointInCmd(self):
        self.importDataPointCsv()
        self.pcs.showDataPointInCmd()
        self.assertEqual(True, True)

    def testRandomSimulation(self):
        self.importDataPointCsv()
        self.pcs.startRandomSimulation()

    def testStopSimulation(self):
        self.importDataPointCsv()
        self.pcs.stopSimulation()

    def testGetValueByAddress(self):
        self.importDataPointCsv()
        self.pcs.server.setValueByAddress(
            1, 40001, 200, self.pcs.server.RegisterType.OUTPUT
        )
        # self.pcs.modbus_server.slaves[1].setValues(4, 1, [3293])
        print(self.pcs.server.slaves[1].getValues(3, 1))
        # print(self.pcs.modbus_server.getValueByAddress(1,40001))

    def testSimulationValue(self):
        self.importDataPointCsv()
        self.pcs.server.start()
        self.pcs.startRandomSimulation()
        while True:
            for i in range(0, len(self.pcs.yc_dict)):
                print(
                    self.pcs.server.getValueByAddress(
                        self.pcs.yc_dict[i].rtu_addr, self.pcs.yc_dict[i].address
                    )
                )

    def testHexValue(self):
        self.importDataPointCsv()
        self.pcs.setHexValue("UA", 100)

    def testAddSerialPcs(self):
        self.pcs = Pcs()
        self.pcs.server.setProtocolType(self.pcs.server.ServerType.Serial)
        self.pcs.importDataPointFromCsv("../point_csv/pcs1_modbus_serial.csv")
        self.pcs.server.start()
        self.assertEqual(True, True)

    def testPlan(self):
        self.pcs = Pcs()
        pcs_path = CSV_DIR + "tuobang_pcs.csv"
        self.pcs.importDataPointFromCsv(pcs_path)
        # 计划需要在点表导入之后
        self.pcs.initPlan()
        self.pcs.plan.importPlanJson()
        self.pcs.initModbusTcpServer(self.pcs.port)
        self.pcs.server.start()
        self.pcs.plan.start()

    def testStartSimulation(self):
        self.pcs = Pcs()
        pcs_path = CSV_DIR + "tuobang_pcs.csv"
        self.pcs.importDataPointFromCsv(pcs_path)
        self.pcs.initModbusTcpServer(self.pcs.port)
        self.pcs.server.start()
        self.pcs.simulation_thread.start()

    def testEditPointData(self):
        self.importDataPointCsv()
        self.pcs.editPointData(1, "isRunning", 100)


if __name__ == "__main__":
    pcs_test = PcsTestCase()
    pcs_test.testAddSerialPcs()
    # unittest.main()
