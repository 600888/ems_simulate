import sys
import os
import unittest

sys.path.append("../../../")

from src.device.dlt645 import Dlt645


class Dlt645TestCase(unittest.TestCase):
    def add_dlt645_serial(self, csv_path):
        dlt645 = Dlt645()
        dlt645.importDataPointFromCsv(csv_path)
        dlt645.server.startServer()
        dlt645.startRandomSimulation()

    def test(self):
        parent_path = os.path.abspath(os.path.join(os.getcwd(), ".."))
        dlt645_serial_path = parent_path + "point_csv/dlt645_serial.csv"
        dlt645 = self.add_dlt645_serial(dlt645_serial_path)


if __name__ == "main":
    dlt645_test = Dlt645TestCase()
    dlt645_test.test()
