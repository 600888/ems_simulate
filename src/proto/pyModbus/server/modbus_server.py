import asyncio
import struct
import logging
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
from src.device.core.message_capture import MessageCapture

# 从子模块导入捕获Framer
from .capture import CreateCaptureSocketFramer, CreateCaptureRtuFramer

class ModbusServer:
    def __init__(
        self,
        logger,
        slave_id_list: List[int],
        port: int = 502,
        protocol_type: ProtocolType = ProtocolType.ModbusTcp,
        serial_port: str = "COM1",
        baudrate: int = 9600,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: int = 1,
        keep_connection: bool = True,
    ):
        self._logger = logger
        self.server = None
        self.protocol_type = protocol_type
        self.ip = "0.0.0.0"
        self.port = port
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.task = None
        self.loop = None
        self.is_running = False
        self.keep_connection = keep_connection
        self.stop_event = asyncio.Event()
        self.message_capture = MessageCapture() # 报文捕获器
        
        # 确保 slave_id_list 包含常用的从站地址 (0, 1)
        all_slave_ids = set(slave_id_list)
        all_slave_ids.add(0)  # 添加广播地址
        all_slave_ids.add(1)  # 添加默认从站地址
        self._slave_id_list = sorted(all_slave_ids)
        self._logger.info(f"Modbus 服务端将响应从站地址: {self._slave_id_list}")
        
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
            for slave_id in self._slave_id_list
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

    def setSerialConfig(self, port, baudrate=9600, bytesize=8, parity="N", stopbits=1):
        self.serial_port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits

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


        # 如果启用了保持连接功能 (仅限 TCP/UDP)
        if self.keep_connection and self.protocol_type in [
            ProtocolType.ModbusTcp, 
            ProtocolType.ModbusTcpClient, 
            ProtocolType.ModbusUdp,
            ProtocolType.ModbusRtuOverTcp
        ]:
            self._logger.info("保持连接功能已启用，将接收Modbus报文而不断开连接")
            # common_params["handler"] = KeepConnectionHandler
        else:
            # 否则使用基础的捕获处理器
            # common_params["handler"] = CaptureRequestHandler
            pass

        try:
            if self.protocol_type == ProtocolType.ModbusTcp:
                address = (
                    self.ip if self.ip else "",
                    self.port if self.port else None,
                )
                
                # 使用自定义 Frmaer
                framer_cls = CreateCaptureSocketFramer(self.message_capture)
                
                self.server = ModbusTcpServer(
                    address=address,  # listen address
                    framer=framer_cls,
                    **common_params,
                )
            elif self.protocol_type == ProtocolType.ModbusRtuOverTcp:
                address = (
                    self.ip if self.ip else "",
                    self.port if self.port else None,
                )
                
                framer_cls = CreateCaptureRtuFramer(self.message_capture)
                
                self.server = ModbusTcpServer(
                    address=address,  # listen address
                    framer=framer_cls,  # The framer strategy to use
                    **common_params,
                )
            elif self.protocol_type == ProtocolType.ModbusUdp:
                address = (
                    self.ip if self.ip else "",
                    self.port if self.port else None,
                )
                
                framer_cls = CreateCaptureSocketFramer(self.message_capture)
                
                self.server = ModbusUdpServer(
                    address=address,  # listen address
                    framer=framer_cls,
                    **common_params,
                )
            elif self.protocol_type == ProtocolType.ModbusRtu:
                serial_params = {
                    "port": self.serial_port,
                    "baudrate": self.baudrate,
                    "bytesize": self.bytesize,
                    "parity": self.parity,
                    "stopbits": self.stopbits,
                }
                self._logger.info(f"启动 Modbus RTU 服务器: {serial_params}")
                
                framer_cls = CreateCaptureRtuFramer(self.message_capture)
                
                self.server = ModbusSerialServer(
                    framer=framer_cls,
                    **common_params,
                    **serial_params,
                )
            elif self.protocol_type == ProtocolType.Tls:
                address = (
                    self.ip if self.ip else "",
                    self.port if self.port else None,
                )
                tls_params = {
                    "host": "localhost",
                    "address": address,
                    "certfile": helper.get_certificate("crt"),
                    "keyfile": helper.get_certificate("key"),
                }
                self.server = ModbusTlsServer(
                    **common_params,
                    **tls_params,
                )
            
            if self.server:
                await self.server.serve_forever()
            else:
                self._logger.error(f"无法初始化服务器: {self.protocol_type}")
        except Exception as e:
            self._logger.error(f"运行 Modbus 服务器失败 ({self.protocol_type}): {e}")
            raise e

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
        
        # 检查 server 是否存在
        if not self.server:
            self._logger.warning("服务器实例不存在，无需停止")
            return
            
        try:
            # 主动关闭所有活动连接
            if hasattr(self.server, 'active_connections'):
                for conn in list(self.server.active_connections.values()):
                    try:
                        conn.close()
                    except Exception as e:
                        self._logger.debug(f"关闭连接时出错: {e}")
                self.server.active_connections.clear()
            
            # 使用pymodbus提供的shutdown函数停止服务器
            await self.server.shutdown()
            self._logger.info("Modbus服务器已停止")
        except Exception as e:
            self._logger.error(f"停止服务器时出错: {e}")

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

    def getCapturedMessages(self, limit: int = 100):
        """获取捕获的报文"""
        return self.message_capture.get_messages(limit)

    def clearCapturedMessages(self) -> None:
        """清空捕获的报文"""
        self.message_capture.clear()

    def add_slave(self, slave_id: int):
        """动态添加从站"""
        if slave_id in self.slaves:
            self._logger.warning(f"从站 {slave_id} 已存在")
            return

        # 创建新的从站上下文
        from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext
        self.slaves[slave_id] = ModbusSlaveContext(
            di=ModbusSequentialDataBlock(0, [0] * 65535),
            co=ModbusSequentialDataBlock(0, [0] * 65535),
            hr=ModbusSequentialDataBlock(0, [0] * 65535),
            ir=ModbusSequentialDataBlock(0, [0] * 65535),
        )
        # 更新 ServerContext
        # 注意: pymodbus 的 ModbusServerContext 可能没有直接提供 add/remove slave 的公开接口
        # 但通常可以通过修改 slaves 字典 (如果是非 single 模式)
        if hasattr(self.context, '__setitem__'):
             self.context[slave_id] = self.slaves[slave_id]
        else:
             # 如果 context 是对象且有 slaves 属性
             if hasattr(self.context, 'slaves') and isinstance(self.context.slaves, dict):
                 self.context.slaves[slave_id] = self.slaves[slave_id]
        
        if slave_id not in self._slave_id_list:
            self._slave_id_list.append(slave_id)
            self._slave_id_list.sort()
            
        self._logger.info(f"已动态添加从站: {slave_id}")

    def remove_slave(self, slave_id: int):
        """动态移除从站"""
        if slave_id not in self.slaves:
            self._logger.warning(f"从站 {slave_id} 不存在")
            return

        del self.slaves[slave_id]
        
        # 更新 ServerContext
        try:
            if hasattr(self.context, '__delitem__'):
                 del self.context[slave_id]
            else:
                 if hasattr(self.context, 'slaves') and isinstance(self.context.slaves, dict):
                     if slave_id in self.context.slaves:
                        del self.context.slaves[slave_id]
        except KeyError:
            self._logger.warning(f"从站 {slave_id} 在 ServerContext 中不存在 (但在 slaves 中存在)")
        except Exception as e:
             self._logger.error(f"从 ServerContext 移除从站 {slave_id} 失败: {e}")

        if slave_id in self._slave_id_list:
            self._slave_id_list.remove(slave_id)
            
        self._logger.info(f"已动态移除从站: {slave_id}")

    def setValueByAddress(
        self,
        func_code,
        rtu_addr,
        address,
        value,
        decode="0x41",  # 默认解析码
    ):
        """
        根据解析码(decode)判断数据类型并设置寄存器值
        使用 DecodeInfo 统一配置处理
        """
        func_code = int(func_code)
        rtu_addr = int(rtu_addr)

        # 检查 slave context 是否存在
        if rtu_addr not in self.slaves:
            self._logger.error(f"setValueByAddress: rtu_addr {rtu_addr} 不在 slaves 中, 现有 slaves: {list(self.slaves.keys())}")
            return

        # 获取解析码完整信息
        info = Decode.get_info(decode)
        pack_format = info.pack_format
        register_cnt = info.register_cnt
        
        # 使用统一的打包方法
        packed = Decode.pack_value(pack_format, value)
        
        # 将打包后的字节转换为寄存器值列表
        if register_cnt == 4:  # 64位
            registers = list(struct.unpack(">HHHH" if info.is_big_endian else "<HHHH", packed))
        elif register_cnt == 2:  # 32位
            registers = list(struct.unpack(">HH" if info.is_big_endian else "<HH", packed))
        else:  # 16位
            # 对于16位数据，直接使用打包后的值
            val = int(value)
            if info.is_signed and val < 0:
                val = (1 << 16) + val
            registers = [val & 0xFFFF]
            if not info.is_big_endian:  # 小端序处理
                registers[0] = ((registers[0] & 0xFF) << 8) | ((registers[0] >> 8) & 0xFF)

        # 设置寄存器值
        if func_code == 10:
            func_code = 6
        self.slaves[rtu_addr].setValues(func_code, address, registers)

    def getValueByAddress(
        self,
        func_code,
        rtu_addr,
        address,
        decode="0x41",
    ):
        """
        根据解析码读取并解析寄存器值
        使用 DecodeInfo 统一配置处理
        """
        func_code = int(func_code)
        rtu_addr = int(rtu_addr)
        if func_code == 10:
            func_code = 6

        # 获取解析码完整信息
        info = Decode.get_info(decode)
        register_cnt = info.register_cnt

        # 获取原始寄存器值
        raw_values = self.slaves[rtu_addr].getValues(func_code, address, register_cnt)
        if not raw_values:
            return 0

        # 将寄存器值打包为字节
        if register_cnt == 4:  # 64位
            packed = struct.pack(">HHHH" if info.is_big_endian else "<HHHH", *raw_values)
        elif register_cnt == 2:  # 32位
            packed = struct.pack(">HH" if info.is_big_endian else "<HH", *raw_values)
        else:  # 16位
            value = raw_values[0]
            if not info.is_big_endian:  # 小端序处理
                value = ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)
            if info.is_signed and value > 0x7FFF:
                value -= 0x10000
            return value
        
        # 使用统一的解包方法
        return Decode.unpack_value(info.pack_format, packed)

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
