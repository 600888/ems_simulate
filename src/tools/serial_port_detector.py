"""
串口检测工具类
提供系统串口的动态检测功能
"""

import serial.tools.list_ports


class SerialPortDetector:
    """串口检测器"""

    @classmethod
    def get_available_ports(cls) -> list[dict[str, str]]:
        """
        获取系统中所有可用的串口

        Returns:
            串口列表，每个元素包含 device 和 description
        """
        ports = []
        for port in serial.tools.list_ports.comports():
            ports.append({"device": port.device, "description": port.description, "hwid": port.hwid})
        return ports

    @classmethod
    def get_port_names(cls) -> list[str]:
        """
        获取系统中所有可用串口的名称列表

        Returns:
            串口名称列表，如 ['COM1', 'COM3', 'COM5']
        """
        return [port.device for port in serial.tools.list_ports.comports()]
