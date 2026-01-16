from typing import Optional
import asyncio
from src.data.service.yc_service import YcService
from src.device.device import Device
from src.enums.modbus_def import ProtocolType
from src.enums.data_source import DataSource
from src.proto.iec104.iec104client import IEC104Client
from src.proto.iec104.iec104server import IEC104Server
from src.proto.pyModbus.client import ModbusClient
from src.proto.pyModbus.server import ModbusServer


class GeneralDeviceBuilder:
    def __init__(
        self,
        device_code,
        import_method=DataSource.Db,
        device: Device = Device(),
    ) -> None:
        self.general_device: Device = device
        self.device_id: int = 0
        self.device_name: str = ""
        self.device_code: str = device_code
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

    def initPlan(self) -> None:
        self.general_device.initPlan()

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
        if (
            protocol_type == ProtocolType.ModbusTcp
            or protocol_type == ProtocolType.ModbusRtuOverTcp
        ):
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

    @property
    def generalDeviceIec104Server(self) -> Device:
        print("初始化104服务器")
        self.setDeviceId(self.device_id)
        self.setDeviceName(name=self.device_name)
        if self.import_method == DataSource.Db:
            self.general_device.importDataPointFromDb(
                grp_code=self.device_code, protocol_type=self.protocol_type
            )
        else:
            if self.path:
                self.general_device.importDataPointFromCsv(file_name=self.path)
        self.initIec104Server()
        self.general_device.setSpecialDataPointValues()
        self.initPlan()
        if self.is_start and isinstance(self.general_device.server, IEC104Server):
            print(f"start server: {self.general_device.port}")
            self.general_device.server.start()
        return self.general_device

    @property
    def generalDeviceIec104Client(self) -> Device:
        print("初始化104客户端")
        self.setDeviceId(self.device_id)
        self.setDeviceName(name=self.device_name)
        if self.import_method == DataSource.Db:
            self.general_device.importDataPointFromDb(
                grp_code=self.device_code, protocol_type=self.protocol_type
            )
        else:
            if self.path:
                self.general_device.importDataPointFromCsv(file_name=self.path)
        self.initIec104Client()
        self.general_device.setSpecialDataPointValues()
        self.initPlan()
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
        if self.import_method == DataSource.Db:
            self.general_device.importDataPointFromDb(grp_code=self.device_code)
        else:
            if self.path:
                self.general_device.importDataPointFromCsv(file_name=self.path)
        self.initModbusTcpServer()
        self.general_device.setSpecialDataPointValues()
        self.initPlan()
        # 标记服务器需要启动，但实际启动将在有事件循环的地方进行
        # 例如在start_back_end.py的init_device_controller函数中
        return self.general_device

    @property
    def generalDeviceModbusTcpClient(self) -> Device:
        self.setDeviceId(self.device_id)
        self.setDeviceName(name=self.device_name)
        if self.import_method == DataSource.Db:
            self.general_device.importDataPointFromDb(grp_code=self.device_code)
        else:
            if self.path:
                self.general_device.importDataPointFromCsv(file_name=self.path)
        self.initModbusTcpClient()
        self.general_device.setSpecialDataPointValues()
        self.initPlan()
        return self.general_device

    @property
    def generalDeviceSerial(self) -> Device:
        self.setDeviceId(self.device_id)
        self.setDeviceName(name=self.device_name)
        if self.import_method == DataSource.Db:
            self.general_device.importDataPointFromDb(grp_code=self.device_code)
        else:
            if self.path:
                self.general_device.importDataPointFromCsv(file_name=self.path)
        self.initModbusSerialServer()
        self.general_device.setSpecialDataPointValues()
        self.initPlan()
        return self.general_device

    @property
    def generalDeviceDlt645Server(self) -> Device:
        print("初始化dlt645服务端")
        self.setDeviceId(self.device_id)
        self.setDeviceName(name=self.device_name)
        if self.import_method == DataSource.Db:
            self.general_device.importDataPointFromDb(
                grp_code=self.device_code, protocol_type=self.protocol_type
            )
        else:
            if self.path:
                self.general_device.importDataPointFromCsv(file_name=self.path)
        self.general_device.meter_address = YcService.meter_address_dict.get(
            self.device_code, bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        )  # 测点导入后再赋予电表地址
        self.initDlt645Server()
        self.general_device.setSpecialDataPointValues()
        self.initPlan()
        return self.general_device
