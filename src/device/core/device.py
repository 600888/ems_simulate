"""
Device 类 - 设备模拟器核心类
使用组合模式，将职责分离到各个专用组件
"""

import os
import time
import asyncio
import struct
from dataclasses import dataclass, field
from typing import Any, Literal, Union, Optional, Dict, List, Tuple

from src.config.global_config import ROOT_DIR
from src.config.log.device_logger import get_device_logger, DeviceLoggerManager
from src.data.service.point_service import PointService
from src.device.data_update.data_update_thread import DataUpdateThread
from src.device.simulator.simulation_controller import SimulationController
from src.device.core.point_manager import PointManager
from src.device.core.data_exporter import DataExporter
from src.device.protocol.base_handler import ProtocolHandler, ServerHandler, ClientHandler
from src.device.protocol.modbus_handler import ModbusServerHandler, ModbusClientHandler
from src.device.protocol.iec104_handler import IEC104ServerHandler, IEC104ClientHandler
from src.device.protocol.dlt645_handler import DLT645ServerHandler, DLT645ClientHandler
from src.enums.point_data import SimulateMethod, Yc, Yx, Yt, Yk, DeviceType, BasePoint
from src.enums.modbus_def import ProtocolType
from src.enums.modbus_register import Decode


@dataclass
class AddressGroup:
    """地址分组 - 用于批量读取优化
    
    将连续地址的测点分组，以便一次性读取多个寄存器。
    
    Attributes:
        start_address: 起始寄存器地址
        register_count: 需要读取的寄存器数量
        points: 该组包含的测点列表
    """
    start_address: int
    register_count: int
    points: List[BasePoint] = field(default_factory=list)


class Device:
    """设备模拟器核心类"""

    def __init__(self, protocol_type: ProtocolType = ProtocolType.ModbusTcp) -> None:
        """初始化设备实例
        
        Args:
            protocol_type: 协议类型
        """
        # 基本属性
        self.device_id: int = 0
        self.name: str = ""
        self.ip: str = "0.0.0.0"
        self.port: int = 0
        self.serial_port: Optional[str] = None  # 串口号（用于RTU模式）
        self.baudrate: int = 9600
        self.databits: int = 8
        self.stopbits: int = 1
        self.parity: str = "E"
        self.meter_address: str = "000000000000"
        self.device_type: DeviceType = DeviceType.Other
        self.protocol_type: ProtocolType = protocol_type

        # 组合模块
        self.point_manager: PointManager = PointManager()
        self.protocol_handler: Optional[ProtocolHandler] = None
        self.simulation_controller: SimulationController = SimulationController(self)
        self.data_exporter: DataExporter = DataExporter(self.point_manager)

        # 日志（延迟初始化，在 set_name 或 initLog 时创建）
        self._logger = None
        self._logger_initialized = False
        
        # 其他
        self.plan: Optional[Any] = None
        self.data_update_thread: DataUpdateThread = DataUpdateThread(
            task=self.update_data
        )

    # ===== 只读属性（向后兼容） =====

    @property
    def yc_dict(self) -> Dict[int, List[Yc]]:
        """获取遥测字典"""
        return self.point_manager.yc_dict

    @property
    def yx_dict(self) -> Dict[int, List[Yx]]:
        """获取遥信字典"""
        return self.point_manager.yx_dict

    @property
    def slave_id_list(self) -> List[int]:
        """获取从机 ID 列表"""
        return self.point_manager.slave_id_list

    @property
    def codeToDataPointMap(self) -> Dict[str, BasePoint]:
        """获取编码到测点的映射"""
        return self.point_manager.code_map

    @property
    def server(self):
        """获取底层服务器对象"""
        if isinstance(self.protocol_handler, ServerHandler):
            return self.protocol_handler.server
        return None

    @property
    def client(self):
        """获取底层客户端对象"""
        if isinstance(self.protocol_handler, ClientHandler):
            return self.protocol_handler.client
        return None

    def is_protocol_running(self) -> bool:
        """统一获取协议运行状态
        
        Returns:
            bool: 协议是否正在运行
        """
        if self.protocol_handler:
            return self.protocol_handler.is_running
        return False

    # ===== 协议处理 =====

    def _create_protocol_handler(self) -> ProtocolHandler:
        """根据协议类型创建处理器"""
        handler_map = {
            ProtocolType.ModbusTcp: lambda: ModbusServerHandler(self.log),
            ProtocolType.ModbusRtu: lambda: ModbusServerHandler(self.log),
            ProtocolType.ModbusRtuOverTcp: lambda: ModbusServerHandler(self.log),
            ProtocolType.ModbusTcpClient: lambda: ModbusClientHandler(self.log),
            ProtocolType.Iec104Server: lambda: IEC104ServerHandler(self.log),
            ProtocolType.Iec104Client: lambda: IEC104ClientHandler(self.log),
            ProtocolType.Dlt645Server: lambda: DLT645ServerHandler(self.log),
            ProtocolType.Dlt645Client: lambda: DLT645ClientHandler(self.log),
        }
        creator = handler_map.get(self.protocol_type)
        if creator:
            return creator()
        return ModbusServerHandler(self.log)

    def initProtocol(self) -> None:
        """初始化协议处理器"""
        self.protocol_handler = self._create_protocol_handler()
        
        config = {
            "ip": self.ip,
            "port": self.port,
            "serial_port": self.serial_port,
            "baudrate": self.baudrate,
            "databits": self.databits,
            "stopbits": self.stopbits,
            "parity": self.parity,
            "slave_id_list": self.slave_id_list,
            "protocol_type": self.protocol_type,
            "meter_address": self.meter_address,
        }
        self.protocol_handler.initialize(config)
        
        # 添加测点
        all_points = self.point_manager.get_all_points()
        self.protocol_handler.add_points(all_points)

    # 向后兼容的初始化方法
    def initModbusTcpServer(
        self, port: int, protocol_type: ProtocolType = ProtocolType.ModbusTcp
    ) -> None:
        """初始化 Modbus TCP 服务器"""
        self.port = port
        self.protocol_type = protocol_type
        self.initProtocol()

    def initModbusTcpClient(self, ip: str, port: int) -> None:
        """初始化 Modbus TCP 客户端"""
        self.ip = ip
        self.port = port
        self.protocol_type = ProtocolType.ModbusTcpClient
        self.initProtocol()

    def initModbusSerialServer(self) -> None:
        """初始化 Modbus RTU 服务器（串口）"""
        self.protocol_type = ProtocolType.ModbusRtu
        self.initProtocol()

    def initIec104Server(self) -> None:
        """初始化 IEC104 服务器"""
        self.protocol_type = ProtocolType.Iec104Server
        self.initProtocol()

    def initIec104Client(self) -> None:
        """初始化 IEC104 客户端"""
        self.protocol_type = ProtocolType.Iec104Client
        self.initProtocol()

    def initDlt645Server(self) -> None:
        """初始化 DLT645 服务器"""
        self.protocol_type = ProtocolType.Dlt645Server
        self.initProtocol()

    def initDlt645Client(self) -> None:
        """初始化 DLT645 客户端"""
        self.protocol_type = ProtocolType.Dlt645Client
        self.initProtocol()

    # ===== 设备启停 =====

    async def start(self) -> bool:
        """启动设备"""
        try:
            if self.protocol_handler:
                return await self.protocol_handler.start()
            return False
        except Exception as e:
            self.log.error(f"启动设备失败: {e}")
            return False

    async def stop(self) -> bool:
        """停止设备"""
        try:
            if self.protocol_handler:
                return await self.protocol_handler.stop()
            return False
        except Exception as e:
            self.log.error(f"停止设备失败: {e}")
            return False

    # ===== 数据更新 =====

    def update_data(self) -> None:
        """更新设备数据"""
        for slave_id in self.slave_id_list:
            yc_list = self.yc_dict.get(slave_id, [])
            yx_list = self.yx_dict.get(slave_id, [])
            self.getSlaveRegisterValues(yc_list, yx_list)
        time.sleep(1)

    def getSlaveRegisterValues(
        self, yc_list: List[Yc], yx_list: List[Yx]
    ) -> None:
        """从协议处理器获取寄存器值"""
        if not self.protocol_handler:
            return

        for point in yc_list + yx_list:
            try:
                value = self.protocol_handler.read_value(point)
                if value is not None:
                    point.value = value
                    point.is_valid = True
                else:
                    point.is_valid = False
            except (ConnectionError, Exception) as e:
                # 连接失败时静默处理，不中断线程
                point.is_valid = False
                pass

    async def getSlaveRegisterValuesAsync(
        self, yc_list: List[Yc], yx_list: List[Yx], interval_ms: int = 0
    ) -> Tuple[int, int]:
        """从协议处理器获取寄存器值（异步版，支持批量读取优化）
        
        Args:
            yc_list: 遥测列表
            yx_list: 遥信列表
            interval_ms: 每次批量读取请求之间的间隔(毫秒)
            
        Returns:
            Tuple[int, int]: (成功点数, 失败点数)
        
        对于 Modbus 客户端，会将连续地址的测点合并为一次批量读取请求。
        对于其他协议或服务端，回退到逐点读取模式。
        """
        if not self.protocol_handler:
            if self._logger: 
                self._logger.warning("getSlaveRegisterValuesAsync: No protocol handler")
            return 0, 0

        all_points = yc_list + yx_list
        if not all_points:
            return 0, 0
        
        # 检查是否是 Modbus 客户端，支持批量读取
        is_modbus_client = isinstance(self.protocol_handler, ModbusClientHandler)
        
        if is_modbus_client and hasattr(self.protocol_handler, 'read_registers_batch_async'):
            # 使用批量读取优化
            return await self._batch_read_async(all_points, interval_ms=interval_ms)
        else:
            # 回退到逐点读取
            return await self._single_read_async(all_points)

    async def _single_read_async(self, points: List[BasePoint]) -> Tuple[int, int]:
        """逐点读取模式（回退方案）"""
        success_count = 0
        fail_count = 0
        for point in points:
            try:
                if hasattr(self.protocol_handler, 'read_value_async'):
                    value = await self.protocol_handler.read_value_async(point)
                else:
                    value = self.protocol_handler.read_value(point)

                if value is not None:
                    point.value = value
                    point.is_valid = True
                    success_count += 1
                else:
                    point.is_valid = False
                    fail_count += 1
            except (ConnectionError, Exception) as e:
                self.log.error(f"Error reading point {point.code}: {e}")
                point.is_valid = False
                fail_count += 1
        return success_count, fail_count

    async def _batch_read_async(self, points: List[BasePoint], interval_ms: int = 0) -> Tuple[int, int]:
        """批量读取模式（优化方案）
        
        将连续地址的测点分组，一次性读取多个寄存器，然后解码映射。
        
        Args:
            points: 测点列表
            interval_ms: 每次请求之间的间隔(毫秒)
            
        Returns:
            Tuple[int, int]: (成功点数, 失败点数)
        """
        # 1. 按 (slave_id, func_code) 分组
        groups = self._group_points_by_address(points)
        
        success_count = 0
        fail_count = 0
        
        is_first_request = True
        for (slave_id, func_code), address_groups in groups.items():
            for group in address_groups:
                try:
                    # 在请求之间添加间隔（第一次请求不等待）
                    if not is_first_request and interval_ms > 0:
                        await asyncio.sleep(interval_ms / 1000.0)
                    is_first_request = False
                    
                    # 2. 批量读取寄存器
                    registers = await self.protocol_handler.read_registers_batch_async(
                        func_code, slave_id, group.start_address, group.register_count
                    )
                    
                    if registers:
                        # 3. 解码并映射到测点
                        self._decode_batch_registers(registers, group.points, group.start_address)
                        success_count += len(group.points)
                    else:
                        # 读取失败，标记所有测点无效
                        for point in group.points:
                            point.is_valid = False
                        fail_count += len(group.points)
                            
                except Exception as e:
                    self.log.error(f"Batch read error for slave={slave_id}, func={func_code}: {e}")
                    for point in group.points:
                        point.is_valid = False
                    fail_count += len(group.points)
        
        return success_count, fail_count

    def _group_points_by_address(
        self, 
        points: List[BasePoint],
        max_gap: int = 0,
        max_count: int = 120
    ) -> Dict[Tuple[int, int], List[AddressGroup]]:
        """将测点按 (slave_id, func_code) 分组，并找出连续的地址段
        
        Args:
            points: 测点列表
            max_gap: 允许的最大地址间隙（默认0，即必须严格连续）
            max_count: 每次批量读取的最大寄存器数量（默认120）
            
        Returns:
            字典：{(slave_id, func_code): [AddressGroup, ...]}
        """
        # 按 (slave_id, func_code) 分组
        grouped: Dict[Tuple[int, int], List[BasePoint]] = {}
        for point in points:
            if not hasattr(point, 'rtu_addr') or not hasattr(point, 'func_code'):
                continue
            key = (point.rtu_addr, point.func_code)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(point)
        
        result: Dict[Tuple[int, int], List[AddressGroup]] = {}
        
        for key, point_list in grouped.items():
            # 按地址排序
            point_list.sort(key=lambda p: p.address)
            
            address_groups: List[AddressGroup] = []
            current_group: Optional[AddressGroup] = None
            
            for point in point_list:
                # 获取该测点占用的寄存器数量
                decode_info = Decode.get_info(point.decode)
                point_reg_count = decode_info.register_cnt
                point_end_addr = point.address + point_reg_count
                
                if current_group is None:
                    # 新建分组
                    current_group = AddressGroup(
                        start_address=point.address,
                        register_count=point_reg_count,
                        points=[point]
                    )
                else:
                    current_end = current_group.start_address + current_group.register_count
                    
                    # 计算合并后的新结束地址和数量
                    new_end = max(current_end, point_end_addr)
                    new_count = new_end - current_group.start_address
                    
                    # 检查是否连续或在允许的间隙内，且总数量不超过限制
                    # 只有当 point.address <= current_end + max_gap 时才合并
                    # max_gap=0 时，要求 point.address <= current_end (实际上因为已排序，即 == current_end)
                    if point.address <= current_end + max_gap and new_count <= max_count:
                        # 扩展当前分组
                        if point_end_addr > current_end:
                             current_group.register_count = new_count
                        current_group.points.append(point)
                    else:
                        # 保存当前分组，开始新分组
                        address_groups.append(current_group)
                        current_group = AddressGroup(
                            start_address=point.address,
                            register_count=point_reg_count,
                            points=[point]
                        )
            
            # 保存最后一个分组
            if current_group:
                address_groups.append(current_group)
            
            result[key] = address_groups
            
            # 日志记录优化效果
            if len(point_list) > 1:
                total_points = len(point_list)
                total_groups = len(address_groups)
                self.log.debug(
                    f"Batch optimization: {total_points} points -> {total_groups} requests "
                    f"(slave={key[0]}, func={key[1]})"
                )
        
        return result

    def _decode_batch_registers(
        self, 
        registers: List[int], 
        points: List[BasePoint], 
        start_address: int
    ) -> None:
        """将批量读取的寄存器值解码并映射到测点
        
        Args:
            registers: 读取到的寄存器值列表
            points: 需要解码的测点列表
            start_address: 寄存器起始地址
        """
        for point in points:
            try:
                # 计算该测点在寄存器数组中的偏移
                offset = point.address - start_address
                decode_info = Decode.get_info(point.decode)
                reg_count = decode_info.register_cnt
                
                # 检查偏移是否有效
                if offset < 0 or offset + reg_count > len(registers):
                    point.is_valid = False
                    if self._logger:
                        self._logger.warning(
                            f"Invalid offset for point {point.code}: offset={offset}, "
                            f"reg_count={reg_count}, total_regs={len(registers)}"
                        )
                    continue
                
                # 提取该测点对应的寄存器
                point_registers = registers[offset:offset + reg_count]
                
                # 解码寄存器值
                value = self._decode_registers(point_registers, decode_info)
                
                if value is not None:
                    point.value = value
                    point.is_valid = True
                else:
                    point.is_valid = False
                    
            except Exception as e:
                self.log.error(f"Error decoding point {point.code}: {e}")
                point.is_valid = False

    def _decode_registers(self, registers: List[int], decode_info) -> Optional[Union[int, float]]:
        """将寄存器值解码为实际值
        
        Args:
            registers: 寄存器值列表
            decode_info: 解码配置信息
            
        Returns:
            解码后的值
        """
        if not registers:
            return None
            
        reg_count = decode_info.register_cnt
        
        try:
            if reg_count == 4:  # 64位
                packed = struct.pack(
                    ">HHHH" if decode_info.is_big_endian else "<HHHH", 
                    *registers[:4]
                )
            elif reg_count == 2:  # 32位
                packed = struct.pack(
                    ">HH" if decode_info.is_big_endian else "<HH", 
                    *registers[:2]
                )
            else:  # 16位
                value = registers[0]
                if not decode_info.is_big_endian:
                    value = ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)
                if decode_info.is_signed and value > 0x7FFF:
                    value -= 0x10000
                return value
            
            # 使用 Decode 的解包方法
            return Decode.unpack_value(decode_info.pack_format, packed)
            
        except Exception as e:
            self.log.error(f"Decode error: {e}, registers={registers}")
            return None


    # ===== 自动读取控制 =====

    def start_auto_read(self) -> bool:
        """启动自动读取线程
        
        Returns:
            bool: 启动是否成功
        """
        return self.data_update_thread.start()

    def stop_auto_read(self) -> None:
        """停止自动读取线程"""
        self.data_update_thread.stop()

    def is_auto_read_running(self) -> bool:
        """检查自动读取是否正在运行
        
        Returns:
            bool: 是否正在运行
        """
        return self.data_update_thread.is_alive()

    async def single_read(self, event_emitter=None, interval_ms: int = 0) -> Dict[str, int]:
        """执行单次读取操作
        
        Args:
            event_emitter: 进度事件发送器
            interval_ms: 批量读取时每次请求之间的间隔(毫秒)
            
        Returns:
            Dict[str, int]: {'success': int, 'fail': int}
        """
        success_total = 0
        fail_total = 0
        total_slaves = len(self.slave_id_list)
        
        for index, slave_id in enumerate(self.slave_id_list):
            yc_list = self.yc_dict.get(slave_id, [])
            yx_list = self.yx_dict.get(slave_id, [])

            # 读取数据（传递间隔参数）
            s_count, f_count = await self.getSlaveRegisterValuesAsync(yc_list, yx_list, interval_ms=interval_ms)
            success_total += s_count
            fail_total += f_count
            
        return {'success': success_total, 'fail': fail_total}

    def read_single_point(self, point_code: str) -> Optional[float]:
        """读取单个测点的值
        
        Args:
            point_code: 测点编码
            
        Returns:
            Optional[float]: 读取成功返回值，失败返回None
        """
        point = self.point_manager.get_point_by_code(point_code)
        if not point:
            self.log.error(f"{self.name} 未找到测点: {point_code}")
            return None
        
        if not self.protocol_handler:
            return None
        
        try:
            value = self.protocol_handler.read_value(point)
            if value is not None:
                point.value = value
                point.is_valid = True
                return point.real_value if hasattr(point, 'real_value') else float(value)
            else:
                point.is_valid = False
        except Exception as e:
            self.log.error(f"读取测点 {point_code} 失败: {e}")
            point.is_valid = False
        
        return None

    async def read_single_point_async(self, point_code: str) -> Optional[float]:
        """异步读取单个测点的值
        
        Args:
            point_code: 测点编码
            
        Returns:
            Optional[float]: 读取成功返回值，失败返回None
        """
        point = self.point_manager.get_point_by_code(point_code)
        if not point:
            self.log.error(f"{self.name} 未找到测点: {point_code}")
            return None
        
        if not self.protocol_handler:
            return None
        
        try:
            value = await self.protocol_handler.read_value_async(point)
            if value is not None:
                point.value = value
                point.is_valid = True
                return point.real_value if hasattr(point, 'real_value') else float(value)
            else:
                point.is_valid = False
        except Exception as e:
            self.log.error(f"异步读取测点 {point_code} 失败: {e}")
            point.is_valid = False
        
        return None

    # ===== 测点操作 =====

    def editPointData(self, point_code: str, real_value: float) -> bool:
        """编辑测点值"""
        point = self.point_manager.get_point_by_code(point_code)
        if not point:
            self.log.error(f"{self.name} 未找到测点: {point_code}")
            return False

        if not point.set_real_value(real_value):
            return False

        if self.protocol_handler:
            return self.protocol_handler.write_value(point, point.value)
        return True

    async def edit_point_data_async(self, point_code: str, real_value: float) -> bool:
        """异步编辑测点值"""
        point = self.point_manager.get_point_by_code(point_code)
        if not point:
            self.log.error(f"{self.name} 未找到测点: {point_code}")
            return False

        if not point.set_real_value(real_value):
            return False

        if self.protocol_handler:
            if hasattr(self.protocol_handler, 'write_value_async'):
                return await self.protocol_handler.write_value_async(point, point.value)
            # 降级到同步方法（可能会阻塞）
            return self.protocol_handler.write_value(point, point.value)
        return True

    def edit_point_metadata(self, point_code: str, metadata: dict) -> bool:
        """编辑测点元数据"""
        point = self.point_manager.get_point_by_code(point_code)
        if not point:
            return False

        # 记录是否需要重新同步值到协议处理器
        need_resync = False
        current_real_value = getattr(point, 'real_value', None)

        # 1. 更新内存配置
        if "name" in metadata and metadata["name"]:
            point.name = metadata["name"]
        if "rtu_addr" in metadata and str(metadata["rtu_addr"]) != "":
            point.rtu_addr = int(metadata["rtu_addr"])
        if "reg_addr" in metadata and metadata["reg_addr"]:
            addr_str = metadata["reg_addr"]
            point.address = int(addr_str, 16) if addr_str.startswith("0x") else int(addr_str)
            need_resync = True  # 地址变更需要重新同步
        if "func_code" in metadata and str(metadata["func_code"]) != "":
            point.func_code = int(metadata["func_code"])
            need_resync = True  # 功能码变更需要重新同步
        if "decode_code" in metadata and metadata["decode_code"]:
            old_decode = point.decode
            point.decode = metadata["decode_code"]
            if old_decode != metadata["decode_code"]:
                need_resync = True  # 解析码变更需要重新同步
        
        if isinstance(point, (Yc, Yt)):
            if "mul_coe" in metadata and str(metadata["mul_coe"]) != "":
                old_mul_coe = point.mul_coe
                point.mul_coe = float(metadata["mul_coe"])
                if old_mul_coe != float(metadata["mul_coe"]):
                    need_resync = True  # 乘法系数变更需要重新同步
            if "add_coe" in metadata and str(metadata["add_coe"]) != "":
                old_add_coe = point.add_coe
                point.add_coe = float(metadata["add_coe"])
                if old_add_coe != float(metadata["add_coe"]):
                    need_resync = True  # 加法系数变更需要重新同步

        # 处理 code 修改
        if "code" in metadata and metadata["code"] and metadata["code"] != point_code:
            new_code = metadata["code"]
            # 更新 PointManager 的映射
            self.point_manager.code_map[new_code] = self.point_manager.code_map.pop(point_code)
            point.code = new_code

        # 3. 如果配置发生变更，重新将当前值写入协议处理器
        if need_resync and current_real_value is not None and self.protocol_handler:
            try:
                # 使用新的配置重新计算并写入寄存器值
                if point.set_real_value(current_real_value):
                    self.protocol_handler.write_value(point, point.value)
                    self.log.info(f"测点 {point.code} 元数据更新后已重新同步值到协议处理器")
            except Exception as e:
                self.log.warning(f"重新同步测点 {point.code} 值失败: {e}")

        # 4. 更新数据库
        return PointService.update_point_metadata(point_code, metadata)

    def edit_point_limit(
        self, point_code: str, min_value_limit: int, max_value_limit: int
    ) -> bool:
        """编辑测点限值"""
        point = self.point_manager.get_point_by_code(point_code)
        if not point or not isinstance(point, Yc):
            return False

        point.max_value_limit = max_value_limit
        point.min_value_limit = min_value_limit
        return PointService.update_point_limit(
            self.name, point_code, min_value_limit, max_value_limit
        )

    def get_point_data(
        self, point_code_list: List[str]
    ) -> Optional[BasePoint]:
        """获取测点"""
        for code in point_code_list:
            point = self.point_manager.get_point_by_code(code)
            if point:
                return point
        return None

    def resetPointValues(self) -> None:
        """重置所有测点值"""
        self.point_manager.reset_all_values()

    # ===== 动态测点/从机管理 =====

    def add_point_dynamic(self, channel_id: int, frame_type: int, point_data: dict) -> bool:
        """动态添加测点
        
        Args:
            channel_id: 通道ID
            frame_type: 测点类型 (0=遥测, 1=遥信, 2=遥控, 3=遥调)
            point_data: 测点数据
            
        Returns:
            是否添加成功
        """
        try:
            from src.data.dao.point_dao import PointDao
            from src.data.service.yc_service import YcService
            from src.data.service.yx_service import YxService
            from src.data.service.yk_service import YkService
            from src.data.service.yt_service import YtService
            
            # 1. 写入数据库
            db_point = PointDao.create_point(channel_id, frame_type, point_data)
            if not db_point:
                return False
            
            # 2. 转换为内存对象
            point: BasePoint
            slave_id = point_data.get("rtu_addr", 1)
            
            if frame_type == 0:  # 遥测
                point = YcService._create_point(db_point, self.protocol_type)
            elif frame_type == 1:  # 遥信
                point = YxService._create_point(db_point, self.protocol_type)
            elif frame_type == 2:  # 遥控
                point = YkService._create_point(db_point, self.protocol_type)
            elif frame_type == 3:  # 遥调
                point = YtService._create_point(db_point, self.protocol_type)
            else:
                return False
            
            # 3. 添加到测点管理器
            self.point_manager.add_point(slave_id, point)
            
            # 4. 添加到模拟控制器
            self.simulation_controller.add_point(point, SimulateMethod.Random, 1)
            self.simulation_controller.set_point_status(point, True)
            
            # 5. 添加到协议处理器
            if self.protocol_handler:
                # IEC104 协议需要重新初始化
                if self.protocol_type in [ProtocolType.Iec104Server, ProtocolType.Iec104Client]:
                    self._reinit_protocol_for_iec104()
                else:
                    self.protocol_handler.add_points([point])
            
            self.log.info(f"动态添加测点成功: {point_data.get('code')}")
            return True
            
        except Exception as e:
            self.log.error(f"动态添加测点失败: {e}")
            return False

    def add_points_dynamic_batch(self, channel_id: int, frame_type: int, points_data_list: List[dict]) -> bool:
        """动态批量添加测点
        
        Args:
            channel_id: 通道ID
            frame_type: 测点类型 (0=遥测, 1=遥信, 2=遥控, 3=遥调)
            points_data_list: 测点数据列表
            
        Returns:
            是否添加成功
        """
        try:
            from src.data.dao.point_dao import PointDao
            from src.data.service.yc_service import YcService
            from src.data.service.yx_service import YxService
            from src.data.service.yk_service import YkService
            from src.data.service.yt_service import YtService
            
            # 1. 批量写入数据库
            db_points = PointDao.create_points_batch(channel_id, frame_type, points_data_list)
            if not db_points:
                return False
            
            memory_points = []
            
            # 2. 批量转换为内存对象
            for db_point in db_points:
                point: BasePoint
                # slave_id is part of db_point dict now
                slave_id = db_point.get("rtu_addr", 1)
                
                if frame_type == 0:
                    point = YcService._create_point(db_point, self.protocol_type)
                elif frame_type == 1:
                    point = YxService._create_point(db_point, self.protocol_type)
                elif frame_type == 2:
                    point = YkService._create_point(db_point, self.protocol_type)
                elif frame_type == 3:
                    point = YtService._create_point(db_point, self.protocol_type)
                else:
                    return False
                
                # 3. 添加到测点管理器
                self.point_manager.add_point(slave_id, point)
                
                # 4. 添加到模拟控制器
                self.simulation_controller.add_point(point, SimulateMethod.Random, 1)
                self.simulation_controller.set_point_status(point, True)
                
                memory_points.append(point)

            # 5. 添加到协议处理器
            if self.protocol_handler:
                if self.protocol_type in [ProtocolType.Iec104Server, ProtocolType.Iec104Client]:
                    self._reinit_protocol_for_iec104()
                else:
                    self.protocol_handler.add_points(memory_points)
            
            self.log.info(f"动态批量添加 {len(memory_points)} 个测点成功")
            return True
            
        except Exception as e:
            self.log.error(f"动态批量添加测点失败: {e}")
            return False

    def delete_point_dynamic(self, point_code: str) -> bool:
        """动态删除测点
        
        Args:
            point_code: 测点编码
            
        Returns:
            是否删除成功
        """
        try:
            from src.data.dao.point_dao import PointDao
            
            # 1. 从数据库删除
            if not PointDao.delete_point_by_code(point_code):
                return False
            
            # 2. 从测点管理器删除
            point = self.point_manager.get_point_by_code(point_code)
            if point:
                # 从对应的列表中移除
                slave_id = point.rtu_addr
                if isinstance(point, Yc) and slave_id in self.point_manager.yc_dict:
                    self.point_manager.yc_dict[slave_id] = [
                        p for p in self.point_manager.yc_dict[slave_id] if p.code != point_code
                    ]
                elif isinstance(point, Yx) and slave_id in self.point_manager.yx_dict:
                    self.point_manager.yx_dict[slave_id] = [
                        p for p in self.point_manager.yx_dict[slave_id] if p.code != point_code
                    ]
                elif isinstance(point, Yk) and slave_id in self.point_manager.yk_dict:
                    self.point_manager.yk_dict[slave_id] = [
                        p for p in self.point_manager.yk_dict[slave_id] if p.code != point_code
                    ]
                elif isinstance(point, Yt) and slave_id in self.point_manager.yt_dict:
                    self.point_manager.yt_dict[slave_id] = [
                        p for p in self.point_manager.yt_dict[slave_id] if p.code != point_code
                    ]
                
                # 从 code_map 移除
                if point_code in self.point_manager.code_map:
                    del self.point_manager.code_map[point_code]
            
            # 3. IEC104 协议需要重新初始化（如果需要）
            if self.protocol_type in [ProtocolType.Iec104Server, ProtocolType.Iec104Client]:
                self._reinit_protocol_for_iec104()
            
            self.log.info(f"动态删除测点成功: {point_code}")
            return True
            
        except Exception as e:
            self.log.error(f"动态删除测点失败: {e}")
            return False

    def clear_points_by_slave(self, slave_id: int) -> int:
        """清空指定从机的所有测点
        
        Args:
            slave_id: 从机地址
            
        Returns:
            删除的测点数量
        """
        try:
            from src.data.dao.point_dao import PointDao
            
            deleted_count = 0
            
            # 收集该从机下的所有测点 code
            point_codes = []
            
            # 从 yc_dict 收集
            if slave_id in self.point_manager.yc_dict:
                for point in self.point_manager.yc_dict[slave_id]:
                    point_codes.append(point.code)
            
            # 从 yx_dict 收集
            if slave_id in self.point_manager.yx_dict:
                for point in self.point_manager.yx_dict[slave_id]:
                    point_codes.append(point.code)
            
            # 从 yk_dict 收集
            if slave_id in self.point_manager.yk_dict:
                for point in self.point_manager.yk_dict[slave_id]:
                    point_codes.append(point.code)
            
            # 从 yt_dict 收集
            if slave_id in self.point_manager.yt_dict:
                for point in self.point_manager.yt_dict[slave_id]:
                    point_codes.append(point.code)
            
            # 批量删除
            for code in point_codes:
                # 从数据库删除
                if PointDao.delete_point_by_code(code):
                    deleted_count += 1
                # 从 code_map 移除
                if code in self.point_manager.code_map:
                    del self.point_manager.code_map[code]
            
            # 清空内存中的测点列表
            if slave_id in self.point_manager.yc_dict:
                self.point_manager.yc_dict[slave_id] = []
            if slave_id in self.point_manager.yx_dict:
                self.point_manager.yx_dict[slave_id] = []
            if slave_id in self.point_manager.yk_dict:
                self.point_manager.yk_dict[slave_id] = []
            if slave_id in self.point_manager.yt_dict:
                self.point_manager.yt_dict[slave_id] = []
            
            # IEC104 协议需要重新初始化
            if self.protocol_type in [ProtocolType.Iec104Server, ProtocolType.Iec104Client]:
                self._reinit_protocol_for_iec104()
            
            self.log.info(f"清空从机 {slave_id} 的测点成功，共删除 {deleted_count} 个测点")
            
            return deleted_count
            
        except Exception as e:
            self.log.error(f"清空从机测点失败: {e}")
            return 0

    def add_slave_dynamic(self, slave_id: int) -> bool:
        """动态添加从机
        
        Args:
            slave_id: 从机地址 (1-255)
            
        Returns:
            是否添加成功
        """
        try:
            from src.data.service.slave_service import SlaveService
            
            if slave_id < 0 or slave_id > 255:
                self.log.error(f"无效的从机地址: {slave_id}")
                return False
            
            if slave_id in self.point_manager.slave_id_list:
                self.log.warning(f"从机 {slave_id} 已存在")
                return False
            
            # 1. 持久化到数据库
            if not SlaveService.create_slave(self.device_id, slave_id):
                self.log.error(f"保存从机到数据库失败: {slave_id}")
                return False
            
            # 2. 添加到内存中的从机列表
            self.point_manager.slave_id_list.append(slave_id)
            self.point_manager.slave_id_list.sort()
            
            # 3. 同步更新底层协议服务器 (Modbus)
            if self.server and hasattr(self.server, "add_slave"):
                self.server.add_slave(slave_id)
            
            self.log.info(f"动态添加从机成功: {slave_id}")
            return True
            
        except Exception as e:
            self.log.error(f"动态添加从机失败: {e}")
            return False


    def delete_slave_dynamic(self, slave_id: int) -> bool:
        """动态删除从机
        
        Args:
            slave_id: 从机地址
            
        Returns:
            是否删除成功
        """
        try:
            from src.data.service.slave_service import SlaveService

            if slave_id not in self.point_manager.slave_id_list:
                self.log.warning(f"从机 {slave_id} 不存在")
                return False
            
            # 1. 从数据库删除从机记录
            if not SlaveService.delete_slave(self.device_id, slave_id):
                self.log.error(f"从数据库删除从机失败: {slave_id}")
                return False

            # 2. 清空该从机的所有测点
            self.clear_points_by_slave(slave_id)
            
            # 3. 从列表中移除
            self.point_manager.slave_id_list.remove(slave_id)
            
            # 4. 同步更新底层协议服务器 (Modbus)
            if self.server and hasattr(self.server, "remove_slave"):
                self.server.remove_slave(slave_id)
            
            # 5. 如果是 IEC104，需要重新初始化 (已在 clear_slave_points 中部分处理，但主要是因为点没了)
            # 这里 slave_id_list 变了，也需要更新
            if self.protocol_type in [ProtocolType.Iec104Server, ProtocolType.Iec104Client]:
                self._reinit_protocol_for_iec104()
            
            self.log.info(f"动态删除从机成功: {slave_id}")
            return True
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.log.error(f"动态删除从机失败: {e}")
            return False

    def edit_slave_dynamic(self, old_slave_id: int, new_slave_id: int) -> bool:
        """动态编辑从机（修改从机地址）
        
        Args:
            old_slave_id: 旧从机地址
            new_slave_id: 新从机地址
            
        Returns:
            是否编辑成功
        """
        try:
            from src.data.service.slave_service import SlaveService

            if old_slave_id not in self.point_manager.slave_id_list:
                self.log.warning(f"从机 {old_slave_id} 不存在")
                return False
                
            if new_slave_id < 0 or new_slave_id > 255:
                self.log.error(f"无效的新从机地址: {new_slave_id}")
                return False

            if old_slave_id == new_slave_id:
                return True
                
            if new_slave_id in self.point_manager.slave_id_list:
                self.log.warning(f"从机 {new_slave_id} 已存在，无法修改为该地址")
                return False
            
            # 1. 更新数据库中的从机地址
            if not SlaveService.update_slave_id(self.device_id, old_slave_id, new_slave_id):
                self.log.error(f"更新从机地址到数据库失败: {old_slave_id} -> {new_slave_id}")
                return False
                
            # 2. 迁移测点字典
            # 移动内存中的列表
            if old_slave_id in self.point_manager.yc_dict:
                self.point_manager.yc_dict[new_slave_id] = self.point_manager.yc_dict.pop(old_slave_id)
            else:
                self.point_manager.yc_dict[new_slave_id] = []

            if old_slave_id in self.point_manager.yx_dict:
                self.point_manager.yx_dict[new_slave_id] = self.point_manager.yx_dict.pop(old_slave_id)
            else:
                self.point_manager.yx_dict[new_slave_id] = []

            if old_slave_id in self.point_manager.yk_dict:
                self.point_manager.yk_dict[new_slave_id] = self.point_manager.yk_dict.pop(old_slave_id)
            else:
                self.point_manager.yk_dict[new_slave_id] = []
                
            if old_slave_id in self.point_manager.yt_dict:
                self.point_manager.yt_dict[new_slave_id] = self.point_manager.yt_dict.pop(old_slave_id)
            else:
                self.point_manager.yt_dict[new_slave_id] = []

            # 3. 更新内存中所有测点对象的 slave_id
            # get_points_by_slave 返回的是 tuple(list, list, list, list)
            points_tuple = self.point_manager.get_points_by_slave(new_slave_id)
            for point_list in points_tuple:
                for point in point_list:
                    # print(point)
                    point.slave_id = new_slave_id
                    point.rtu_addr = new_slave_id
            
            # 4. 持久化到数据库 (测点表中的 rtu_addr)
            # 使用 DAO 批量更新
            from src.data.dao.point_dao import PointDao
            # device_id 存储的是 channel_id
            PointDao.update_slave_id(self.device_id, old_slave_id, new_slave_id)

            # 5. 更新 slave_id_list
            if old_slave_id in self.point_manager.slave_id_list:
                self.point_manager.slave_id_list.remove(old_slave_id)
            
            if new_slave_id not in self.point_manager.slave_id_list:
                self.point_manager.slave_id_list.append(new_slave_id)
                self.point_manager.slave_id_list.sort()
            
            # 6. 同步更新底层协议服务器 (Modbus)
            if self.server and hasattr(self.server, "add_slave") and hasattr(self.server, "remove_slave"):
                self.server.add_slave(new_slave_id)
                self.server.remove_slave(old_slave_id)

            # 7. 协议重置 (IEC104)
            if self.protocol_type in [ProtocolType.Iec104Server, ProtocolType.Iec104Client]:
                self._reinit_protocol_for_iec104()
                
            self.log.info(f"动态编辑从机成功: {old_slave_id} -> {new_slave_id}")
            return True
            
        except Exception as e:
            self.log.error(f"动态编辑从机失败: {e}")
            return False

    def _reinit_protocol_for_iec104(self) -> None:
        """重新初始化 IEC104 协议处理器"""
        if self.protocol_handler:
            # 重新创建处理器并初始化
            self.protocol_handler = self._create_protocol_handler()
            config = {
                "ip": self.ip,
                "port": self.port,
                "serial_port": self.serial_port,
                "baudrate": self.baudrate,
                "databits": self.databits,
                "stopbits": self.stopbits,
                "parity": self.parity,
                "slave_id_list": self.slave_id_list,
                "protocol_type": self.protocol_type,
                "meter_address": self.meter_address,
            }
            self.protocol_handler.initialize(config)
            all_points = self.point_manager.get_all_points()
            self.protocol_handler.add_points(all_points)

    # ===== 模拟控制 =====

    def setAllPointSimulateMethod(self, simulate_method: Union[str, SimulateMethod]) -> None:
        """设置所有点的模拟方法"""
        try:
            method = SimulateMethod(simulate_method)
            self.simulation_controller.set_all_point_simulate_method(method)
        except ValueError:
            self.log.error(f"无效的模拟方法: {simulate_method}")

    def setSinglePointSimulateMethod(
        self, point_code: str, simulate_method: Union[str, SimulateMethod]
    ) -> bool:
        """设置单个点的模拟方法"""
        try:
            method = SimulateMethod(simulate_method)
            return self.simulation_controller.set_single_point_simulate_method(
                point_code, method
            )
        except ValueError:
            self.log.error(f"无效的模拟方法: {simulate_method}")
            return False

    def setSinglePointStep(self, point_code: str, step: int) -> bool:
        return self.simulation_controller.set_single_point_step(point_code, step)

    def getPointInfo(self, point_code: str) -> Dict:
        return self.simulation_controller.get_point_info(point_code)

    def setPointSimulationRange(
        self, point_code: str, min_value: float, max_value: float
    ) -> bool:
        return self.simulation_controller.set_point_simulation_range(
            point_code, min_value, max_value
        )

    def startSimulation(self) -> None:
        self.simulation_controller.start_simulation()

    def stopSimulation(self) -> None:
        self.simulation_controller.stop_simulation()

    def isSimulationRunning(self) -> bool:
        return self.simulation_controller.is_simulation_running()

    def initSimulationPointList(self) -> None:
        """初始化模拟点列表"""
        for point in self.point_manager.get_all_points():
            self.simulation_controller.add_point(point, SimulateMethod.Random, 1)
            self.simulation_controller.set_point_status(point, True)

    def setSpecialDataPointValues(self) -> None:
        """设置特殊数据点值（子类可重写）"""
        pass

    # ===== 数据导入导出 =====

    def importDataPointFromChannel(
        self, channel_id: int, protocol_type: ProtocolType = ProtocolType.ModbusTcp
    ) -> None:
        """从通道导入测点"""
        self.protocol_type = protocol_type
        self.point_manager.import_from_db(channel_id, protocol_type)
        self.initSimulationPointList()
        self.initLog()

    def importDataPointFromCsv(self, file_name: str) -> None:
        """从 CSV 导入测点"""
        self.data_exporter.import_csv(file_name)
        self.initSimulationPointList()
        self.initLog()

    def exportDataPointCsv(self, file_path: str) -> None:
        self.data_exporter.export_csv(file_path)

    def exportDataPointXlsx(self, file_path: str) -> None:
        self.data_exporter.export_xlsx(file_path)

    def get_table_head(self) -> List[str]:
        return self.data_exporter.get_table_head()

    def get_table_data(
        self,
        slave_id: int,
        name: Optional[str] = None,
        page_index: Optional[int] = 1,
        page_size: Optional[int] = 10,
        point_types: Optional[List[int]] = None,
    ) -> tuple[List[List[str]], int]:
        # 对于 IEC104 客户端，在获取表格数据前同步 c104.Point 的值到内部点
        if self.protocol_type == ProtocolType.Iec104Client and self.protocol_handler:
            self._sync_iec104_client_values(slave_id)
        
        # Determine if we should mask errors (only for Client devices)
        mask_error = self.protocol_type in [
            ProtocolType.ModbusTcpClient,
            ProtocolType.Iec104Client,
            ProtocolType.Dlt645Client
        ]

        return self.data_exporter.get_table_data(
            slave_id, name, page_index, page_size, point_types, mask_error=mask_error
        )

    def _sync_iec104_client_values(self, slave_id: int) -> None:
        """同步 IEC104 客户端从服务端接收的值到内部测点
        
        当服务端主动上报数据时，c104.Point 对象的 .value 会自动更新，
        此方法将这些值同步到应用内部的测点对象。
        """
        try:
            from src.device.protocol.iec104_handler import IEC104ClientHandler
            from src.enums.point_data import Yc
            
            if not isinstance(self.protocol_handler, IEC104ClientHandler):
                return
            
            if not self.protocol_handler._is_running:
                return
            
            client = self.protocol_handler._client
            if not client or not client.station:
                return
            
            # 获取该从机下的所有测点 (yc, yx, yt, yk)
            yc_list, yx_list, yt_list, yk_list = self.point_manager.get_points_by_slave(slave_id)
            all_points = yc_list + yx_list + yt_list + yk_list
            
            for point in all_points:
                try:
                    # 直接从 c104.Point 对象读取值（服务端上报时自动更新）
                    c104_point = client.station.get_point(io_address=point.address)
                    if c104_point is None:
                        continue
                    
                    real_val = c104_point.value
                    if real_val is not None:
                        # 遥测点需要反向换算
                        if isinstance(point, Yc):
                            try:
                                raw_val = int((float(real_val) - point.add_coe) / point.mul_coe)
                                point.value = raw_val
                            except (ZeroDivisionError, TypeError):
                                pass
                        else:
                            point.value = real_val
                except Exception as e:
                    self.log.debug(f"同步测点 {point.code} 失败: {e}")
        except Exception as e:
            self.log.error(f"IEC104 客户端数据同步失败: {e}")

    # ===== 报文捕获 =====

    def get_messages(self, limit: Optional[int] = None) -> List[dict]:
        """获取报文历史记录
        
        从协议处理器获取原始报文。
        
        Args:
            limit: 最大返回数量，None表示返回全部
            
        Returns:
            报文记录列表（字典格式）
        """
        if self.protocol_handler and hasattr(self.protocol_handler, 'get_captured_messages'):
            messages = self.protocol_handler.get_captured_messages(limit or 100)
            if messages:
                # 判断是否为客户端模式
                is_client = self.protocol_type in [
                    ProtocolType.ModbusTcpClient,
                    ProtocolType.Iec104Client,
                    ProtocolType.Dlt645Client
                ]

                # 统一显示格式
                result = []
                for msg in messages:
                    direction = msg.get("direction", "")
                    # 推导报文类型 (Request/Response)
                    msg_type = ""
                    if is_client:
                        # 客户端: TX是请求, RX是响应
                        msg_type = "Request" if direction == "TX" else "Response"
                    else:
                        # 服务端: RX是请求, TX是响应
                        msg_type = "Request" if direction == "RX" else "Response"

                    result.append({
                        "sequence_id": msg.get("sequence_id", 0),
                        "timestamp": msg.get("timestamp", 0),
                        "formatted_time": msg.get("time", msg.get("formatted_time", "")),
                        "direction": direction,
                        "msg_type": msg_type, # 新增报文类型
                        "hex_data": msg.get("hex_string", msg.get("data", "")),
                        "raw_hex": msg.get("data", ""),
                        "description": msg.get("description", ""),
                        "length": msg.get("length", 0)
                    })
                
                # 按序号正序排列（旧的在前，符合 Request -> Response 顺序）
                # 如果有sequence_id，使用sequence_id排序，否则使用timestamp
                result.sort(key=lambda x: (x.get("sequence_id", 0), x["timestamp"]), reverse=False)
                return result[:limit] if limit else result
        
        return []
    
    def clear_messages(self) -> None:
        """清空报文历史记录"""
        if self.protocol_handler and hasattr(self.protocol_handler, 'clear_captured_messages'):
            self.protocol_handler.clear_captured_messages()

    # ===== 日志 =====

    @property
    def log(self):
        """获取设备日志器（延迟初始化）
        
        使用 loguru 的 bind() 模式，每个设备有独立的日志上下文。
        日志文件自动路由到 log/{device_name}/{device_name}.log
        """
        if self._logger is None:
            device_name = self.name or "unknown_device"
            self._logger = get_device_logger(device_name, auto_register=self._logger_initialized)
        return self._logger

    def initLog(self) -> None:
        """初始化日志
        
        注册设备日志处理器，创建独立的日志文件。
        调用后该设备的日志将写入 log/{device_name}/{device_name}.log
        """
        if self.name:
            DeviceLoggerManager.register_device(
                self.name,
                log_level="INFO",
                rotation="1 MB",
                retention="7 days",
            )
            self._logger_initialized = True
            # 重新获取日志器以确保使用新配置
            self._logger = get_device_logger(self.name, auto_register=False)
            self.log.info(f"设备 {self.name} 日志已初始化")

    # ===== 辅助方法 =====

    def set_device_id(self, device_id: int) -> None:
        self.device_id = device_id

    def set_name(self, name: str) -> None:
        self.name = name

    @staticmethod
    def frame_type_dict() -> Dict[int, str]:
        return PointManager.frame_type_dict()

    @staticmethod
    def set_frame_type(is_yc: bool, func_code: int) -> int:
        is_common_func = func_code in [1, 2, 3, 4]
        if is_yc:
            return 0 if is_common_func else 3
        else:
            return 1 if is_common_func else 2

    @staticmethod
    def get_value_by_bit(value: int, bit: int) -> int:
        return (value >> bit) & 1

    # ===== 事件处理 =====

    def on_point_value_changed(self, sender: Any, **extra: Any) -> None:
        """处理测点值变化事件"""
        old_point = extra.get("old_point")
        related_point = extra.get("related_point")

        if not old_point or not related_point:
            return

        try:
            if old_point.related_value is None:
                change_value = (
                    old_point.value
                    if isinstance(old_point, Yx)
                    else old_point.real_value
                )
            else:
                key = (
                    old_point.value
                    if isinstance(old_point, Yx)
                    else int(old_point.real_value)
                )
                change_value = old_point.related_value.get(key)
                if change_value is None:
                    return

            self.editPointData(related_point.code, change_value)
        except Exception as e:
            self.log.error(f"处理点值变化事件失败: {e}")

    def setRelatedPoint(
        self, point: BasePoint, related_point: BasePoint
    ) -> None:
        """设置测点关联"""
        if not point or not related_point:
            return

        point.related_point = related_point
        point.is_send_signal = True
        point.value_changed.connect(self.on_point_value_changed)
