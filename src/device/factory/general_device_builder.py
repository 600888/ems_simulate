"""
通用设备构建器
负责根据配置创建和初始化设备实例
"""

from typing import Optional
import asyncio

from src.data.service.point_service import PointService
from src.data.service.channel_service import ChannelService
from src.data.service.yc_service import YcService
from src.data.service.yx_service import YxService
from src.data.service.yk_service import YkService
from src.data.service.yt_service import YtService
from src.device.core.device import Device
from src.enums.modbus_def import ProtocolType
from src.enums.data_source import DataSource
from src.proto.iec104.iec104client import IEC104Client
from src.proto.iec104.iec104server import IEC104Server
from src.proto.pyModbus.client import ModbusClient
from src.proto.pyModbus.server import ModbusServer


class GeneralDeviceBuilder:
    """通用设备构建器"""

    def __init__(
        self,
        channel_id: int,
        import_method=DataSource.Db,
        device: Device = None,
    ) -> None:
        self.general_device: Device = device if device else Device()
        self.device_id: int = 0
        self.device_name: str = ""
        self.channel_id: int = channel_id
        self.import_method: DataSource = import_method
        self.path: Optional[str] = None
        self.serial_port: Optional[str] = None
        self.is_start: bool = False
        self.protocol_type: ProtocolType = ProtocolType.ModbusTcp

    def setDeviceId(self, device_id: int) -> None:
        self.general_device.set_device_id(device_id)

    def setDeviceName(self, name: str) -> None:
        self.general_device.set_name(name)

    def setDeviceNetConfig(self, port: int, ip: str = "0.0.0.0") -> None:
        self.general_device.port = port
        self.general_device.ip = ip

    def setDeviceSerialConfig(
        self, 
        serial_port: str, 
        baudrate: int = 9600, 
        databits: int = 8, 
        stopbits: int = 1, 
        parity: str = "E"
    ) -> None:
        """设置串口配置"""
        self.general_device.serial_port = serial_port
        self.general_device.baudrate = baudrate
        self.general_device.databits = databits
        self.general_device.stopbits = stopbits
        self.general_device.parity = parity

    def initModbusTcpClient(self) -> None:
        self.general_device.initModbusTcpClient(
            self.general_device.ip, self.general_device.port
        )

    def initModbusTcpServer(self) -> None:
        self.general_device.initModbusTcpServer(
            self.general_device.port, self.protocol_type
        )

    def initModbusSerialServer(self) -> None:
        self.general_device.initModbusSerialServer()

    def initIec104Server(self) -> None:
        self.general_device.initIec104Server()

    def initIec104Client(self) -> None:
        self.general_device.initIec104Client()

    def initDlt645Server(self) -> None:
        self.general_device.initDlt645Server()

    def initDlt645Client(self) -> None:
        self.general_device.initDlt645Client()

    def importDataPoints(self) -> None:
        """导入测点数据"""
        if self.import_method == DataSource.Db:
            self.general_device.importDataPointFromChannel(
                channel_id=self.channel_id, protocol_type=self.protocol_type
            )
        elif self.path:
            self.general_device.importDataPointFromCsv(file_name=self.path)

    def makeGeneralDevice(
        self,
        device_id: int,
        device_name: str,
        protocol_type: ProtocolType,
        is_start: bool,
        path: Optional[str] = None,
    ) -> Device | None:
        self.device_id = device_id
        self.device_name = device_name
        self.path = path
        self.is_start = is_start
        self.protocol_type = protocol_type

        if protocol_type in [ProtocolType.ModbusTcp, ProtocolType.ModbusRtuOverTcp]:
            return self.generalDeviceModbusTcp
        elif protocol_type == ProtocolType.ModbusTcpClient:
            return self.generalDeviceModbusTcpClient
        elif protocol_type == ProtocolType.ModbusRtu:
            return self.generalDeviceSerial
        elif protocol_type == ProtocolType.Iec104Server:
            return self.generalDeviceIec104Server
        elif protocol_type == ProtocolType.Iec104Client:
            return self.generalDeviceIec104Client
        elif protocol_type == ProtocolType.Dlt645Server:
            return self.generalDeviceDlt645Server
        elif protocol_type == ProtocolType.Dlt645Client:
            return self.generalDeviceDlt645Client
        return None

    @property
    def generalDeviceIec104Server(self) -> Device:
        self.setDeviceId(self.device_id)
        self.setDeviceName(name=self.device_name)
        self.importDataPoints()
        self.initIec104Server()
        self.general_device.setSpecialDataPointValues()
        if self.is_start and isinstance(self.general_device.server, IEC104Server):
            print(f"start server: {self.general_device.port}")
            self.general_device.server.start()
        return self.general_device

    @property
    def generalDeviceIec104Client(self) -> Device:
        self.setDeviceId(self.device_id)
        self.setDeviceName(name=self.device_name)
        self.importDataPoints()
        self.initIec104Client()
        self.general_device.setSpecialDataPointValues()
        if self.is_start and isinstance(self.general_device.client, IEC104Client):
            print(
                f"start client: {self.general_device.client.ip} port: {self.general_device.client.port}"
            )
            self.general_device.client.connect()
        return self.general_device

    @property
    def generalDeviceModbusTcp(self) -> Device:
        self.setDeviceId(self.device_id)
        self.setDeviceName(name=self.device_name)
        self.importDataPoints()
        self.initModbusTcpServer()
        self.general_device.setSpecialDataPointValues()
        return self.general_device

    @property
    def generalDeviceModbusTcpClient(self) -> Device:
        self.setDeviceId(self.device_id)
        self.setDeviceName(name=self.device_name)
        self.importDataPoints()
        self.initModbusTcpClient()
        self.general_device.setSpecialDataPointValues()
        return self.general_device

    @property
    def generalDeviceSerial(self) -> Device:
        self.setDeviceId(self.device_id)
        self.setDeviceName(name=self.device_name)
        self.importDataPoints()
        self.initModbusSerialServer()
        self.general_device.setSpecialDataPointValues()
        return self.general_device

    @property
    def generalDeviceDlt645Server(self) -> Device:
        print("初始化dlt645服务端")
        self.setDeviceId(self.device_id)
        self.setDeviceName(name=self.device_name)
        self.importDataPoints()
        # 设置电表地址（12位字符串）
        channel = ChannelService.get_channel_by_id(self.channel_id)
        if channel:
            # 从 rtu_addr 字段获取电表地址字符串
            meter_addr = channel.get("rtu_addr", "000000000000")
            self.general_device.meter_address = str(meter_addr) if meter_addr else "000000000000"
        self.initDlt645Server()
        self.general_device.setSpecialDataPointValues()
        return self.general_device

    @property
    def generalDeviceDlt645Client(self) -> Device:
        print("初始化dlt645客户端")
        self.setDeviceId(self.device_id)
        self.setDeviceName(name=self.device_name)
        self.importDataPoints()
        # 设置电表地址（12位字符串）
        channel = ChannelService.get_channel_by_id(self.channel_id)
        if channel:
            meter_addr = channel.get("rtu_addr", "000000000000")
            self.general_device.meter_address = str(meter_addr) if meter_addr else "000000000000"
        self.initDlt645Client()
        self.general_device.setSpecialDataPointValues()
        return self.general_device
