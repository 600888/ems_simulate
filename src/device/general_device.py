from src.device.device import Device, DeviceType


class GeneralDevice(Device):
    def __init__(self):
        super().__init__()
        self.device_type = DeviceType.Other
