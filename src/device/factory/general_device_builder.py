"""
通用设备构建器
负责根据配置创建和初始化设备实例
"""

from src.data.service.channel_service import ChannelService
from src.device.core.device import Device
from src.enums.data_source import DataSource
from src.enums.modbus_def import ProtocolType

# 协议模块延迟导入，减少启动时间
# from src.proto.iec104.iec104client import IEC104Client
# from src.proto.iec104.iec104server import IEC104Server
# from src.proto.pyModbus.client import ModbusClient
# from src.proto.pyModbus.server import ModbusServer


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
        self.path: str | None = None
        self.serial_port: str | None = None
        self.is_start: bool = False
        self.protocol_type: ProtocolType = ProtocolType.ModbusTcpServer

    def setDeviceId(self, device_id: int) -> None:
        self.general_device.set_device_id(device_id)

    def setDeviceName(self, name: str) -> None:
        self.general_device.set_name(name)

    def setDeviceNetConfig(self, port: int, ip: str = "0.0.0.0") -> None:
        self.general_device.port = port
        self.general_device.ip = ip

    def setDeviceModelName(self, model_name: str) -> None:
        """设置设备模型名称 (IEC61850 IED 名称)"""
        self.general_device.model_name = model_name

    def setDeviceIcdPath(self, icd_path: str) -> None:
        """设置设备 ICD 文件路径 (IEC61850, v2.0)"""
        self.general_device.icd_path = icd_path

    def setDeviceRuntimeConfig(self, runtime_config: dict) -> None:
        self.general_device.runtime_config = dict(runtime_config)

    def setDeviceSecurityConfig(self, security_config: dict) -> None:
        self.general_device.security_config = dict(security_config)

    def setDeviceSerialConfig(
        self, serial_port: str, baudrate: int = 9600, databits: int = 8, stopbits: int = 1, parity: str = "E"
    ) -> None:
        """设置串口配置"""
        self.general_device.serial_port = serial_port
        self.general_device.baudrate = baudrate
        self.general_device.databits = databits
        self.general_device.stopbits = stopbits
        self.general_device.parity = parity

    def initModbusTcpClient(self) -> None:
        self.general_device.initModbusTcpClient(self.general_device.ip, self.general_device.port)

    def initModbusTcpServer(self) -> None:
        self.general_device.initModbusTcpServer(self.general_device.port, self.protocol_type)

    def initModbusSerialServer(self) -> None:
        self.general_device.initModbusSerialServer()

    def initModbusSerialClient(self) -> None:
        self.general_device.initModbusSerialClient()

    def initIec104Server(self) -> None:
        self.general_device.initIec104Server()

    def initIec104Client(self) -> None:
        self.general_device.initIec104Client()

    def initDlt645Server(self) -> None:
        self.general_device.initDlt645Server()

    def initDlt645Client(self) -> None:
        self.general_device.initDlt645Client()

    def initIec61850Server(self) -> None:
        self.general_device.initIec61850Server()

    def initIec61850Client(self) -> None:
        self.general_device.initIec61850Client()

    def initDnp3Server(self) -> None:
        self.general_device.initDnp3Server()

    def initDnp3Client(self) -> None:
        self.general_device.initDnp3Client()

    def importDataPoints(self) -> None:
        """导入测点数据"""
        if self.import_method == DataSource.Db:
            self.general_device.importDataPointFromChannel(channel_id=self.channel_id, protocol_type=self.protocol_type)
        elif self.path:
            self.general_device.importDataPointFromCsv(file_name=self.path)

    def makeGeneralDevice(
        self,
        device_id: int,
        device_name: str,
        protocol_type: ProtocolType,
        is_start: bool,
        path: str | None = None,
    ) -> Device | None:
        self.device_id = device_id
        self.device_name = device_name
        self.path = path
        self.is_start = is_start
        self.protocol_type = protocol_type

        if protocol_type in [ProtocolType.ModbusTcpServer, ProtocolType.ModbusRtuOverTcp]:
            return self.generalDeviceModbusTcp
        elif protocol_type == ProtocolType.ModbusTcpClient:
            return self.generalDeviceModbusTcpClient
        elif protocol_type == ProtocolType.ModbusRtuClient:
            return self.generalDeviceSerialClient
        elif protocol_type in [ProtocolType.ModbusRtu, ProtocolType.ModbusRtuServer]:
            return self.generalDeviceSerial
        elif protocol_type == ProtocolType.Iec104Server:
            return self.generalDeviceIec104Server
        elif protocol_type == ProtocolType.Iec104Client:
            return self.generalDeviceIec104Client
        elif protocol_type == ProtocolType.Dlt645Server:
            return self.generalDeviceDlt645Server
        elif protocol_type == ProtocolType.Dlt645Client:
            return self.generalDeviceDlt645Client
        elif protocol_type == ProtocolType.Iec61850Server:
            return self.generalDeviceIec61850Server
        elif protocol_type == ProtocolType.Iec61850Client:
            return self.generalDeviceIec61850Client
        elif protocol_type == ProtocolType.Dnp3Server:
            return self.generalDeviceDnp3Server
        elif protocol_type == ProtocolType.Dnp3Client:
            return self.generalDeviceDnp3Client
        return None

    @property
    def generalDeviceIec104Server(self) -> Device:
        from src.proto.iec104.iec104server import IEC104Server

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
        from src.proto.iec104.iec104client import IEC104Client

        self.setDeviceId(self.device_id)
        self.setDeviceName(name=self.device_name)
        self.importDataPoints()
        self.initIec104Client()
        self.general_device.setSpecialDataPointValues()
        if self.is_start and isinstance(self.general_device.client, IEC104Client):
            print(f"start client: {self.general_device.client.ip} port: {self.general_device.client.port}")
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
    def generalDeviceSerialClient(self) -> Device:
        self.setDeviceId(self.device_id)
        self.setDeviceName(name=self.device_name)
        self.importDataPoints()
        self.initModbusSerialClient()
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

    @property
    def generalDeviceIec61850Server(self) -> Device:
        print("初始化IEC61850服务端")
        self.setDeviceId(self.device_id)
        self.setDeviceName(name=self.device_name)
        # IEC61850 测点来自 ICD 模型文件，不从数据库导入
        self.initIec61850Server()
        self.general_device.initLog()
        self.general_device.setSpecialDataPointValues()
        return self.general_device

    @property
    def generalDeviceIec61850Client(self) -> Device:
        print("初始化IEC61850客户端")
        self.setDeviceId(self.device_id)
        self.setDeviceName(name=self.device_name)
        # IEC61850 测点来自 ICD 模型文件或 MMS 在线发现，不从数据库导入
        self.initIec61850Client()
        self.general_device.initLog()
        self.general_device.setSpecialDataPointValues()
        return self.general_device

    @property
    def generalDeviceDnp3Server(self) -> Device:
        """构建 DNP3 服务端（Outstation）"""

        self.setDeviceId(self.device_id)
        self.setDeviceName(name=self.device_name)
        self.importDataPoints()
        self.initDnp3Server()
        self.general_device.setSpecialDataPointValues()
        # DNP3 为 asyncio 协议，启动由 async handler.start()（device.start()/reload）异步驱动，
        # 不在同步构建方法里直接在事件循环外启动。
        return self.general_device

    @property
    def generalDeviceDnp3Client(self) -> Device:
        """构建 DNP3 客户端（Master）"""

        self.setDeviceId(self.device_id)
        self.setDeviceName(name=self.device_name)
        self.importDataPoints()
        self.initDnp3Client()
        self.general_device.setSpecialDataPointValues()
        # DNP3 为 asyncio 协议，启动由 async handler.start()（device.start()/reload）异步驱动。
        return self.general_device
