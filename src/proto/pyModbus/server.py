import asyncio
import struct
from typing import List

from pymodbus import __version__ as pymodbus_version
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
    ModbusSparseDataBlock,
)
from pymodbus.device import ModbusDeviceIdentification
from pymodbus.server import (
    ModbusTcpServer,
    ModbusUdpServer,
    ModbusSerialServer,
    ModbusTlsServer,
    StartAsyncTcpServer,
    StartAsyncUdpServer,
    StartAsyncSerialServer,
    StartAsyncTlsServer,
)
from pymodbus.framer import ModbusRtuFramer
from pymodbus.server.async_io import ModbusServerRequestHandler

from src.enums.modbus_register import Decode, DecodeType
from src.proto.pyModbus import helper
from src.enums.modbus_def import ProtocolType


class KeepConnectionHandler(ModbusServerRequestHandler):
    """自定义请求处理器，用于保持连接不断开"""

    def __init__(self, request, client_address, server):
        self.server = server
        super().__init__(request, client_address, server)

    async def handle(self):
        """处理请求但不关闭连接"""
        try:
            # 调用父类的handle方法处理请求
            await super().handle()
            # 不调用close()方法，保持连接打开
            if hasattr(self, "close_connection"):
                # 确保不会自动关闭连接
                self.close_connection = False
        except Exception as e:
            self.server._logger.error(f"处理请求时出错: {e}")


class ModbusServer:
    def __init__(
        self,
        logger,
        slave_id_list: List[int],
        port: int,
        protocol_type: ProtocolType = ProtocolType.ModbusTcp,
        keep_connection: bool = False,  # 新增参数：是否保持连接不断开
    ):
        self._logger = logger
        self.server = None
        self.ip = None  # 服务器地址, 默认本机地址
        self.protocol_type = protocol_type  # 服务器类型, 串口, tcp, udp, tls, 默认tcp
        self.ip = "0.0.0.0"
        self.port = port  # 端口号
        self.serial_port = "/dev/ttyUSB0"  # 串口号, 默认/dev/ttyUSB0
        self.task = None
        self.loop = None
        self.is_running = False
        self.keep_connection = keep_connection  # 新增标志位：是否保持连接不断开
        self.stop_event = asyncio.Event()  # 初始化停止事件
        # 创建从站上下文
        self.slaves = {
            slave_id: ModbusSlaveContext(
                di=ModbusSequentialDataBlock(
                    0, [0] * 65535
                ),  # Discrete Inputs 初始化为 0
                co=ModbusSequentialDataBlock(0, [0] * 65535),  # Coils 初始化为 0
                hr=ModbusSequentialDataBlock(
                    0, [0] * 65535
                ),  # Holding Registers 初始化为 0
                ir=ModbusSequentialDataBlock(0, [0] * 65535),
            )  # Input Registers 初始化为 0
            for slave_id in slave_id_list
        }
        self.context = ModbusServerContext(slaves=self.slaves, single=False)

    def setServerAddress(self, address):
        self.ip = address

    def setProtocolType(self, protocol_type):
        self.protocol_type = protocol_type

    def setServerPort(self, port):
        self.port = port

    def setSlaveCnt(self, slave_cnt):
        self.slave_cnt = slave_cnt

    def setUpServer(self, description=None, context=None, cmdline=None):
        """Run server setup."""
        args = helper.get_commandline(
            server=True, description=description, cmdline=cmdline
        )
        if context:
            args.context = context
        if not args.context:
            self._logger.info("### Create datastore")
            if args.store == "sequential":
                datablock = ModbusSequentialDataBlock(0x00, [17] * 100)
            elif args.store == "sparse":
                datablock = ModbusSparseDataBlock({0x00: 0, 0x05: 1})
            elif args.store == "factory":
                datablock = ModbusSequentialDataBlock.create()

            if args.slaves:
                context = {
                    0x01: ModbusSlaveContext(
                        di=datablock,
                        co=datablock,
                        hr=datablock,
                        ir=datablock,
                    ),
                    0x02: ModbusSlaveContext(
                        di=datablock,
                        co=datablock,
                        hr=datablock,
                        ir=datablock,
                    ),
                    0x03: ModbusSlaveContext(
                        di=datablock,
                        co=datablock,
                        hr=datablock,
                        ir=datablock,
                        zero_mode=True,
                    ),
                }
                single = False
            else:
                context = ModbusSlaveContext(
                    di=datablock, co=datablock, hr=datablock, ir=datablock
                )
                single = True

            # Build data storage
            args.context = ModbusServerContext(slaves=context, single=single)

        args.identity = ModbusDeviceIdentification(
            info_name={
                "VendorName": "Pymodbus",
                "ProductCode": "PM",
                "VendorUrl": "https://github.com/pymodbus-dev/pymodbus/",
                "ProductName": "Pymodbus Server",
                "ModelName": "Pymodbus Server",
                "MajorMinorRevision": pymodbus_version,
            }
        )
        return args



    async def runAsyncServer(self, args):
        """Run server."""
        txt = f"### start ASYNC server, listening on {self.port} - {self.protocol_type}"
        self._logger.info(txt)

        # 通用参数
        common_params = {
            "context": args.context,  # Data storage
            "identity": args.identity,  # server identify
        }

        # 如果启用了保持连接功能
        if self.keep_connection:
            self._logger.info("保持连接功能已启用，将接收Modbus报文而不断开连接")
            common_params["handler"] = KeepConnectionHandler

        if self.protocol_type == ProtocolType.ModbusTcp:
            address = (
                self.ip if self.ip else "",
                self.port if self.port else None,
            )
            self.server = ModbusTcpServer(
                address=address,  # listen address
                **common_params,
            )
        elif self.protocol_type == ProtocolType.ModbusRtuOverTcp:
            address = (
                self.ip if self.ip else "",
                self.port if self.port else None,
            )
            self.server = ModbusTcpServer(
                address=address,  # listen address
                framer=ModbusRtuFramer,  # The framer strategy to use
                **common_params,
            )
        elif self.protocol_type == ProtocolType.ModbusUdp:
            address = (
                self.ip if self.ip else "",
                self.port if self.port else None,
            )
            self.server = ModbusUdpServer(
                address=address,  # listen address
                **common_params,
            )
        elif self.protocol_type == ProtocolType.ModbusRtu:
            # socat -d -d PTY,link=/tmp/ptyp0,raw,echo=0,ispeed=9600
            #             PTY,link=/tmp/ttyp0,raw,echo=0,ospeed=9600
            serial_params = {
                "port": self.serial_port,  # serial port
                "stopbits": 1,  # The number of stop bits to use
                "bytesize": 8,  # The bytesize of the serial messages
                "parity": "N",  # Which kind of parity to use
                "baudrate": 9600,  # The baud rate to use for the serial device
            }
            self.server = ModbusSerialServer(
                **common_params,
                **serial_params,
            )
        elif self.protocol_type == ProtocolType.Tls:
            address = (
                self.ip if self.ip else "",
                self.port if self.port else None,
            )
            tls_params = {
                "host": "localhost",  # define tcp address where to connect to.
                "address": address,  # listen address
                "certfile": helper.get_certificate(
                    "crt"
                ),  # The cert file path for TLS (used if sslctx is None)
                "keyfile": helper.get_certificate(
                    "key"
                ),  # The key file path for TLS (used if sslctx is None)
            }
            self.server = ModbusTlsServer(
                **common_params,
                **tls_params,
            )
        await self.server.serve_forever()

    async def initServer(self):
        runArgs = self.setUpServer(
            description="Run callback server.", cmdline=None, context=self.context
        )
        
        # 启动服务器 - pymodbus的StartAsync*Server函数会阻塞运行
        self._logger.info("正在启动Modbus服务器...")
        await self.runAsyncServer(runArgs)

    def startAsyncServer(self):
        # 创建事件循环
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            self.loop.run_until_complete(self.initServer())
        except Exception as e:
            self._logger.error(f"服务器运行出错: {e}")
        finally:
            self.loop.close()

    async def start(self):
        """异步启动服务器"""
        self.is_running = True
        self.stop_event.clear()
        
        try:
            # 使用runAsyncServer直接启动服务器
            runArgs = self.setUpServer(
                description="Run callback server.", cmdline=None, context=self.context
            )
            
            # 启动服务器 - pymodbus的StartAsync*Server函数会阻塞运行直到服务器停止
            await self.runAsyncServer(runArgs)
        except Exception as e:
            if not self.stop_event.is_set():
                self._logger.error(f"服务器运行过程中出错: {e}")
                self.is_running = False
        finally:
            self.is_running = False

    async def stopAsync(self):
        """异步停止服务器"""
        if not self.is_running:
            self._logger.info("服务器已停止")
            return
            
        self._logger.info("停止Modbus服务器")
        self.is_running = False
        self.stop_event.set()
        
        # 使用pymodbus提供的ServerStop函数停止服务器
        await self.server.shutdown()
        self._logger.info("Modbus服务器已停止")

    def startSync(self):
        """同步启动服务器（阻塞调用）"""
        self.is_running = True
        self.stop_event.clear()
        
        # 创建事件循环
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        try:
            # 运行服务器直到停止
            self.loop.run_until_complete(self.start())
        except Exception as e:
            if not self.stop_event.is_set():
                self._logger.error(f"服务器运行过程中出错: {e}")
        finally:
            self.is_running = False
            self.loop.close()
            
    def stop(self):
        """同步停止服务器的方法，用于兼容命令行工具调用"""
        self.stopSync()
    
    def stopSync(self):
        """同步停止服务器"""
        if self.loop and self.loop.is_running():
            # 如果事件循环正在运行，在事件循环中执行停止操作
            self.loop.run_until_complete(self.stopAsync())
        else:
            # 否则直接执行停止操作
            asyncio.run(self.stopAsync())
    
    def setKeepConnection(self, keep: bool):
        """
        设置是否保持连接不断开

        Args:
            keep: True表示保持连接不断开，False表示使用默认行为
        """
        self.keep_connection = keep
        self._logger.info(f"设置保持连接: {keep}")
        # 注意：修改此设置后需要重启服务器才能生效
        return True

    def isRunning(self):
        return self.is_running

    def setValueByAddress(
        self,
        func_code,
        rtu_addr,
        address,
        value,
        decode="0x20",  # 默认解析码
        register_cnt=1,
        signed=False,
    ):
        """
        根据解析码(decode)判断数据类型并设置寄存器值
        """
        func_code = int(func_code)
        rtu_addr = int(rtu_addr)

        # 根据解析码选择处理方式
        decode_type = Decode.get_decode_type(decode)
        endian = Decode.get_endian(decode)
        if register_cnt == 2:
            if decode_type == DecodeType.Float:  # 浮点数处理
                packed = struct.pack(f"{endian}f", float(value))
                registers = list(struct.unpack(f"{endian}HH", packed))
            else:
                fmt = f"{endian}l" if signed else f"{endian}L"
                packed = struct.pack(fmt, int(value))
                registers = list(struct.unpack(f"{endian}HH", packed))
        elif register_cnt == 1:  # 默认16位整数
            value = int(value)
            if signed and value < 0:
                value = (1 << 16) + value
            registers = [value & 0xFFFF]
            # 小端序处理
            if endian == "<":
                registers[0] = ((registers[0] & 0xFF) << 8) | (
                    (registers[0] >> 8) & 0xFF
                )

        # 设置寄存器值
        if func_code == 10:
            func_code = 6
        self.slaves[rtu_addr].setValues(func_code, address, registers)

    def getValueByAddress(
        self,
        func_code,
        rtu_addr,
        address,
        decode="0x20",
        register_cnt=1,
        signed=False,
    ):
        func_code = int(func_code)
        rtu_addr = int(rtu_addr)
        if func_code == 10:
            func_code = 6

        # 获取原始寄存器值（每个寄存器16位）
        raw_values = self.slaves[rtu_addr].getValues(func_code, address, register_cnt)
        if not raw_values:
            return 0

        endian = Decode.get_endian(decode)
        # 数据类型解析逻辑
        if register_cnt == 2:  # 32位数据
            packed = struct.pack(f"{endian}HH", *raw_values)
            if Decode.get_decode_type(decode) == DecodeType.Float:
                return struct.unpack(f"{endian}f", packed)[0]
            else:
                fmt = f"{endian}l" if signed else f"{endian}L"
                return struct.unpack(fmt, packed)[0]
        else:  # 16位数据（新增字节序处理）
            value = raw_values[0]
            if endian == "<":  # 小端序处理
                value = ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)
            if signed and value > 0x7FFF:  # 有符号数补码转换
                value -= 0x10000
            return value

    # 业务部分
    def setAllRegisterValues(self, yc_dict, yx_dict):
        for slave_id in range(0, len(yc_dict)):
            yc_list = yc_dict.get(slave_id)
            # 将遥测数据写入到寄存器中
            for i in range(0, len(yc_list)):
                self.setValueByAddress(
                    yc_list[i].func_code,
                    yc_list[i].rtu_addr,
                    yc_list[i].address,
                    yc_list[i].value,
                )

        for slave_id in range(0, len(yx_dict)):
            yx_list = yx_dict.get(slave_id)
            # 将遥信数据写入到寄存器中
            for i in range(0, len(yx_list)):
                self.setValueByAddress(
                    yx_list[i].func_code,
                    yx_list[i].rtu_addr,
                    yx_list[i].address,
                    yx_list[i].value,
                )
