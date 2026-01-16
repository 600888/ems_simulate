import random
import threading
import time
from dataclasses import dataclass

from src.device.device import Device, DeviceType
from src.tools.import_point import PointImporter


class Bms(Device):
    def __init__(self):
        super().__init__()
        self.clusterList = []
        self.device_type = DeviceType.Bms

    def setSpecialDataPointValues(self):
        # BMS并网命令
        onGridCmd = self.get_point_data(["onGridCmd"])
        connectionStatus = self.get_point_data(["connectionStatus"])
        self.setRelatedPoint(onGridCmd, connectionStatus)
