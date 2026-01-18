from src.device.core.device import Device, DeviceType


class Pcs(Device):
    def __init__(self):
        super().__init__()
        self.device_type = DeviceType.Pcs

    # 计划模拟
    def setSimulatePlanValues(self):
        pass

    def setPcsConfig(self, pcs_config):
        pass

    # 初始预设值
    def initPointValues(self):
        pass
        # self.editPointData("isFault", 0)
        # self.editPointData("isRunning", 1)
        # self.editPointData("isOnGrid", 1)
        # self.editPointData("isRemote", 1)
        # self.editPointData("temperature", 40)
        # self.editPointData("envTemperature", 20)

    def setSpecialDataPointValues(self):
        # 从寄存器中取出特殊测点的值
        setP = self.get_point_data(["setP"])
        totalAcP = self.get_point_data(["totalAcP"])
        self.setRelatedPoint(setP, totalAcP)

        setQ = self.get_point_data(["setQ"])
        totalAcQ = self.get_point_data(["totalAcQ"])
        self.setRelatedPoint(setQ, totalAcQ)

        # 启停机
        powerSwitchCmd = self.get_point_data(["powerSwitchCmd"])
        deviceStatus = self.get_point_data(["deviceStatus"])
        if powerSwitchCmd is not None:
            powerSwitchCmd.related_value = {1: 2, 0: 0}

        self.setRelatedPoint(powerSwitchCmd, deviceStatus)

        # 并离网
        onGridSwitchCmd = self.get_point_data(["onGridSwitchCmd"])
        offGridSwitchCmd = self.get_point_data(["offGridSwitchCmd"])
        if onGridSwitchCmd is not None:
            onGridSwitchCmd.related_value = {1: 2}
        if offGridSwitchCmd is not None:
            offGridSwitchCmd.related_value = {1: 3}  # 下发离网让运行状态变为3
        self.setRelatedPoint(onGridSwitchCmd, deviceStatus)
        self.setRelatedPoint(offGridSwitchCmd, deviceStatus)

        # 故障复位
        resetCmd = self.get_point_data(["resetCmd"])
        isFault = self.get_point_data(["isFault"])
        self.setRelatedPoint(resetCmd, isFault)
