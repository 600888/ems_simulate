import unittest

from src.device.types.bms import Bms


class BmsTestCase(unittest.TestCase):
    def importDataPointCsv(self):
        self.bms = Bms()
        self.bms.initModbusTcpServer(port=10502)
        self.bms.importDataPointFromCsv("../../config/point_csv/linping_bms1.csv")
        self.bms.importClusterDataPoint(
            "../../config/point_csv/linping_bms1_cluster.csv"
        )

    def testExportDataPointCsv(self):
        self.importDataPointCsv()
        self.bms.exportDataPointCsv("../../point_csv/test.csv")

    def testExportDataPointXlsx(self):
        self.importDataPointCsv()
        self.bms.exportDataPointXlsx("../../point_csv/test.xlsx")

    def testShowDataPointInCmd(self):
        self.importDataPointCsv()
        self.bms.showDataPointInCmd()

    def testRandomSimulation(self):
        self.importDataPointCsv()

    # 测试获得系统总电压接口
    def testGetTotalSystemVoltage(self):
        self.importDataPointCsv()
        self.bms.getTotalSystemVoltage()

    # 测试获得系统总电流接口
    def testGetTotalSystemCurrent(self):
        self.importDataPointCsv()
        self.bms.getTotalSystemCurrent()

    # 测试获得系统SOC接口
    def testGetSystemSOC(self):
        self.importDataPointCsv()
        self.bms.getSystemSoc()

    # 测试获取系统平均温度接口
    def testGetSystemAverageTemperature(self):
        self.importDataPointCsv()
        self.bms.getAverageTemperature()

    # 测试获取系统平均电压接口
    def testGetAverageVoltage(self):
        self.importDataPointCsv()
        self.bms.getAverageVoltage()

    # 测试获取系统单体最高温度接口
    def testGetMaxTemperature(self):
        self.importDataPointCsv()
        self.bms.getMaxTemperature()

    # 测试获取系统单体最低温度接口
    def testGetMinTemperature(self):
        self.importDataPointCsv()
        self.bms.getMinTemperature()

    # 测试获取系统单体最高电压接口
    def testGetMaxVoltage(self):
        self.importDataPointCsv()
        self.bms.getMaxVoltage()

    # 测试获取系统单体最低电压接口
    def testGetMinVoltage(self):
        self.importDataPointCsv()
        self.bms.getMinVoltage()

    # 测试获取系统簇间电压差异
    def testGetVoltageDifference(self):
        self.importDataPointCsv()
        self.bms.getVoltageDifference()

    # 测试获取系统单体最高电流
    def testGetMaxCurrent(self):
        self.importDataPointCsv()
        self.bms.getMaxCurrent()

    # 测试获取系统单体最低电流
    def testGetMinCurrent(self):
        self.importDataPointCsv()
        self.bms.getMinCurrent()

    # 测试获取系统簇间电流差异
    def testGetCurrentDifference(self):
        self.importDataPointCsv()
        self.bms.getCurrentDifference()

    # 测试获取系统单体最高电压簇号
    def testGetMaxVoltageClusterNumber(self):
        self.importDataPointCsv()
        self.bms.getMaxVoltageClusterId()

    # 测试设置簇内系统值
    def testSetClusterSystemData(self):
        self.importDataPointCsv()
        self.bms.setClusterSystemValues()

    # 测试导出系统数据点
    def testExportSystemDataPoint(self):
        dataList = []
        self.importDataPointCsv()
        self.bms.exportSystemDataPoint(dataList)
        for i in range(0, len(dataList)):
            print(dataList[i])

    def testImportClusterDataPointCsv(self):
        self.bms = Bms()
        self.importDataPointCsv()
        for i in range(0, len(self.bms.yx_dict)):
            print(
                self.bms.yx_dict[i].name,
                self.bms.yx_dict[i].code,
                self.bms.yx_dict[i].value,
            )

    def testSimulateRandomValues(self):
        self.importDataPointCsv()
        self.bms.setRandomSlaveValues()
        # self.bms.showDataPointInCmd()

    # 根据名称获取测点数据
    def testGetTableDataByName(self):
        self.importDataPointCsv()
        self.bms.server.start()
        table_data = self.bms.get_table_data(slave_id=1, name="总")
        for i in range(0, len(table_data)):
            print(table_data[i])


if __name__ == "__main__":
    unittest.main()
