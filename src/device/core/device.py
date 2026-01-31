"""
Device 类 - 设备模拟器核心类
使用组合模式，将职责分离到各个专用组件
"""

import os
import time
import asyncio
from typing import Any, Literal, Union, Optional, Dict, List

from src.config.global_config import ROOT_DIR
from src.config.log.logger import Log
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

        # 其他
        self.plan: Optional[Any] = None
        self.log: Optional[Log] = None
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
            if self.log:
                self.log.error(f"启动设备失败: {e}")
            return False

    async def stop(self) -> bool:
        """停止设备"""
        try:
            if self.protocol_handler:
                return await self.protocol_handler.stop()
            return False
        except Exception as e:
            if self.log:
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
            except (ConnectionError, Exception) as e:
                # 连接失败时静默处理，不中断线程
                pass

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

    def single_read(self) -> None:
        """执行单次读取操作"""
        for slave_id in self.slave_id_list:
            yc_list = self.yc_dict.get(slave_id, [])
            yx_list = self.yx_dict.get(slave_id, [])
            self.getSlaveRegisterValues(yc_list, yx_list)

    def read_single_point(self, point_code: str) -> Optional[float]:
        """读取单个测点的值
        
        Args:
            point_code: 测点编码
            
        Returns:
            Optional[float]: 读取成功返回值，失败返回None
        """
        point = self.point_manager.get_point_by_code(point_code)
        if not point:
            if self.log:
                self.log.error(f"{self.name} 未找到测点: {point_code}")
            return None
        
        if not self.protocol_handler:
            return None
        
        try:
            value = self.protocol_handler.read_value(point)
            if value is not None:
                point.value = value
                return point.real_value if hasattr(point, 'real_value') else float(value)
        except Exception as e:
            if self.log:
                self.log.error(f"读取测点 {point_code} 失败: {e}")
        
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
            if self.log:
                self.log.error(f"{self.name} 未找到测点: {point_code}")
            return None
        
        if not self.protocol_handler:
            return None
        
        try:
            value = await self.protocol_handler.read_value_async(point)
            if value is not None:
                point.value = value
                return point.real_value if hasattr(point, 'real_value') else float(value)
        except Exception as e:
            if self.log:
                self.log.error(f"异步读取测点 {point_code} 失败: {e}")
        
        return None

    # ===== 测点操作 =====

    def editPointData(self, point_code: str, real_value: float) -> bool:
        """编辑测点值"""
        point = self.point_manager.get_point_by_code(point_code)
        if not point:
            if self.log:
                self.log.error(f"{self.name} 未找到测点: {point_code}")
            return False

        if not point.set_real_value(real_value):
            return False

        if self.protocol_handler:
            return self.protocol_handler.write_value(point, point.value)
        return True

    def edit_point_metadata(self, point_code: str, metadata: dict) -> bool:
        """编辑测点元数据"""
        point = self.point_manager.get_point_by_code(point_code)
        if not point:
            return False

        # 1. 更新内存配置
        if "name" in metadata and metadata["name"]:
            point.name = metadata["name"]
        if "rtu_addr" in metadata and str(metadata["rtu_addr"]) != "":
            point.rtu_addr = int(metadata["rtu_addr"])
        if "reg_addr" in metadata and metadata["reg_addr"]:
            addr_str = metadata["reg_addr"]
            point.address = int(addr_str, 16) if addr_str.startswith("0x") else int(addr_str)
        if "func_code" in metadata and str(metadata["func_code"]) != "":
            point.func_code = int(metadata["func_code"])
        if "decode_code" in metadata and metadata["decode_code"]:
            point.decode = metadata["decode_code"]
        
        if isinstance(point, (Yc, Yt)):
            if "mul_coe" in metadata and str(metadata["mul_coe"]) != "":
                point.mul_coe = float(metadata["mul_coe"])
            if "add_coe" in metadata and str(metadata["add_coe"]) != "":
                point.add_coe = float(metadata["add_coe"])

        # 处理 code 修改
        if "code" in metadata and metadata["code"] and metadata["code"] != point_code:
            new_code = metadata["code"]
            # 更新 PointManager 的映射
            self.point_manager.code_map[new_code] = self.point_manager.code_map.pop(point_code)
            point.code = new_code

        # 2. 更新数据库
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
            
            if self.log:
                self.log.info(f"动态添加测点成功: {point_data.get('code')}")
            return True
            
        except Exception as e:
            if self.log:
                self.log.error(f"动态添加测点失败: {e}")
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
            
            if self.log:
                self.log.info(f"动态删除测点成功: {point_code}")
            return True
            
        except Exception as e:
            if self.log:
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
            
            if self.log:
                self.log.info(f"清空从机 {slave_id} 的测点成功，共删除 {deleted_count} 个测点")
            
            return deleted_count
            
        except Exception as e:
            if self.log:
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
            if slave_id < 1 or slave_id > 255:
                if self.log:
                    self.log.error(f"无效的从机地址: {slave_id}")
                return False
            
            if slave_id in self.point_manager.slave_id_list:
                if self.log:
                    self.log.warning(f"从机 {slave_id} 已存在")
                return False
            
            # 添加到从机列表
            self.point_manager.slave_id_list.append(slave_id)
            self.point_manager.slave_id_list.sort()
            
            if self.log:
                self.log.info(f"动态添加从机成功: {slave_id}")
            return True
            
        except Exception as e:
            if self.log:
                self.log.error(f"动态添加从机失败: {e}")
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
            if self.log:
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
            if self.log:
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
        
        return self.data_exporter.get_table_data(
            slave_id, name, page_index, page_size, point_types
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

    def initLog(self) -> None:
        """初始化日志"""
        log_dir = os.path.join(ROOT_DIR, "log", self.name)
        os.makedirs(log_dir, exist_ok=True)
        self.log = Log(
            filename=os.path.join(log_dir, f"{self.name}.log"),
            cmdlevel="INFO",
            filelevel="INFO",
            limit=1024000,
            backup_count=1,
            colorful=True,
        )

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
            if self.log:
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
