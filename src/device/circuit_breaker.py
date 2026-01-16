from src.device.device import Device, DeviceType


class CircuitBreaker(Device):
    def __init__(self):
        super().__init__()
        self.device_type = DeviceType.CircuitBreaker

    # 初始预设值
    def initPointValues(self):
        pass

    def setSpecialDataPointValues(self):
        # 从寄存器中取出特殊测点的值
        breaker = self.get_point_data(["breaker"])
        breakerStatus = self.get_point_data(["breakerStatus"])
        self.setRelatedPoint(breaker, breakerStatus)
