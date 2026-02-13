"""
Device 类 - 设备模拟器核心类 (Facade)

使用组合模式，将职责分离到各个专用组件：
- PointManager: 测点存储与索引
- DataReader: 数据读取与解码
- PointOperator: 测点增删改查
- SlaveManager: 从机增删改
- DataExporter: 数据导入导出
- SimulationController: 模拟控制
- MessageFormatter: 报文格式化
- ProtocolHandler: 协议处理
"""

import time
from typing import Any, Literal, Union, Optional, Dict, List, Tuple

from src.config.log.device_logger import get_device_logger, DeviceLoggerManager
from src.device.data_update.data_update_thread import DataUpdateThread
from src.device.simulator.simulation_controller import SimulationController
from src.device.core.point.point_manager import PointManager
from src.device.core.data.data_exporter import DataExporter
from src.device.core.data.data_reader import DataReader
from src.device.core.point.point_operator import PointOperator
from src.device.core.slave_manager import SlaveManager
from src.device.core.message.message_formatter import MessageFormatter
from src.device.protocol.base_handler import ProtocolHandler, ServerHandler, ClientHandler
from src.device.protocol.modbus_handler import ModbusServerHandler, ModbusClientHandler
from src.device.protocol.iec104_handler import IEC104ServerHandler, IEC104ClientHandler
from src.device.protocol.dlt645_handler import DLT645ServerHandler, DLT645ClientHandler
from src.enums.point_data import SimulateMethod, Yc, Yx, Yt, Yk, DeviceType, BasePoint
from src.enums.modbus_def import ProtocolType


class Device:
    """设备模拟器核心类 (Facade)
    
    作为统一入口，将各类操作委托给专用组件处理。
    所有公开方法签名保持向后兼容。
    """

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

        # 核心组件
        self.point_manager: PointManager = PointManager()
        self.protocol_handler: Optional[ProtocolHandler] = None
        self.simulation_controller: SimulationController = SimulationController(self)
        self.data_exporter: DataExporter = DataExporter(self.point_manager)

        # 功能组件（持有 self 引用，始终跟踪最新状态）
        self.data_reader: DataReader = DataReader(self)
        self.point_operator: PointOperator = PointOperator(self)
        self.slave_manager: SlaveManager = SlaveManager(self)
        self.message_formatter: MessageFormatter = MessageFormatter(self)

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

    def _build_protocol_config(self) -> dict:
        """构建协议配置字典"""
        return {
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

    def initProtocol(self) -> None:
        """初始化协议处理器"""
        self.protocol_handler = self._create_protocol_handler()
        self.protocol_handler.initialize(self._build_protocol_config())

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

    # ===== 数据读取（委托给 DataReader） =====

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
        """从协议处理器获取数据值"""
        self.data_reader.get_slave_values(yc_list, yx_list)

    async def getSlaveRegisterValuesAsync(
        self, yc_list: List[Yc], yx_list: List[Yx], interval_ms: int = 0
    ) -> Tuple[int, int]:
        """从协议处理器获取数据值（异步版，支持批量读取优化）"""
        return await self.data_reader.get_slave_values_async(
            yc_list, yx_list, interval_ms
        )

    # ===== 自动读取控制 =====

    def start_auto_read(self) -> bool:
        """启动自动读取线程"""
        return self.data_update_thread.start()

    def stop_auto_read(self) -> None:
        """停止自动读取线程"""
        self.data_update_thread.stop()

    def is_auto_read_running(self) -> bool:
        """检查自动读取是否正在运行"""
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

        for slave_id in self.slave_id_list:
            yc_list = self.yc_dict.get(slave_id, [])
            yx_list = self.yx_dict.get(slave_id, [])

            s_count, f_count = await self.getSlaveRegisterValuesAsync(
                yc_list, yx_list, interval_ms=interval_ms
            )
            success_total += s_count
            fail_total += f_count

        return {'success': success_total, 'fail': fail_total}

    # ===== 测点操作（委托给 PointOperator） =====

    def read_single_point(self, point_code: str) -> Optional[float]:
        """读取单个测点的值"""
        return self.point_operator.read_single_point(point_code)

    async def read_single_point_async(self, point_code: str) -> Optional[float]:
        """异步读取单个测点的值"""
        return await self.point_operator.read_single_point_async(point_code)

    def editPointData(self, point_code: str, real_value: float) -> bool:
        """编辑测点值"""
        return self.point_operator.edit_value(point_code, real_value)

    async def edit_point_data_async(self, point_code: str, real_value: float) -> bool:
        """异步编辑测点值"""
        return await self.point_operator.edit_value_async(point_code, real_value)

    def edit_point_metadata(self, point_code: str, metadata: dict) -> bool:
        """编辑测点元数据"""
        return self.point_operator.edit_metadata(point_code, metadata)

    def edit_point_limit(
        self, point_code: str, min_value_limit: int, max_value_limit: int
    ) -> bool:
        """编辑测点限值"""
        return self.point_operator.edit_limit(point_code, min_value_limit, max_value_limit)

    def get_point_data(self, point_code_list: List[str]) -> Optional[BasePoint]:
        """获取测点"""
        return self.point_operator.get_point_data(point_code_list)

    def resetPointValues(self) -> None:
        """重置所有测点值"""
        self.point_manager.reset_all_values()

    # ===== 动态测点/从机管理（委托给组件） =====

    def add_point_dynamic(self, channel_id: int, frame_type: int, point_data: dict) -> bool:
        """动态添加测点"""
        return self.point_operator.add_point_dynamic(channel_id, frame_type, point_data)

    def add_points_dynamic_batch(
        self, channel_id: int, frame_type: int, points_data_list: List[dict]
    ) -> bool:
        """动态批量添加测点"""
        return self.point_operator.add_points_dynamic_batch(
            channel_id, frame_type, points_data_list
        )

    def delete_point_dynamic(self, point_code: str) -> bool:
        """动态删除测点"""
        return self.point_operator.delete_point_dynamic(point_code)

    def clear_points_by_slave(self, slave_id: int) -> int:
        """清空指定从机的所有测点"""
        return self.slave_manager.clear_points_by_slave(slave_id)

    def add_slave_dynamic(self, slave_id: int) -> bool:
        """动态添加从机"""
        return self.slave_manager.add_slave(slave_id)

    def delete_slave_dynamic(self, slave_id: int) -> bool:
        """动态删除从机"""
        return self.slave_manager.delete_slave(slave_id)

    def edit_slave_dynamic(self, old_slave_id: int, new_slave_id: int) -> bool:
        """动态编辑从机（修改从机地址）"""
        return self.slave_manager.edit_slave(old_slave_id, new_slave_id)

    def _reinit_protocol_for_iec104(self) -> None:
        """重新初始化 IEC104 协议处理器"""
        if self.protocol_handler:
            self.protocol_handler = self._create_protocol_handler()
            self.protocol_handler.initialize(self._build_protocol_config())
            all_points = self.point_manager.get_all_points()
            self.protocol_handler.add_points(all_points)

    # ===== 模拟控制（委托给 SimulationController） =====

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

    # ===== 数据导入导出（委托给 DataExporter） =====

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
            ProtocolType.Dlt645Client,
        ]

        return self.data_exporter.get_table_data(
            slave_id, name, page_index, page_size, point_types, mask_error=mask_error
        )

    def _sync_iec104_client_values(self, slave_id: int) -> None:
        """同步 IEC104 客户端从服务端接收的值到内部测点"""
        self.data_reader.sync_iec104_client_values(slave_id)

    # ===== 报文捕获（委托给 MessageFormatter） =====

    def get_messages(self, limit: Optional[int] = None) -> List[dict]:
        """获取报文历史记录"""
        return self.message_formatter.get_messages(limit)

    def clear_messages(self) -> None:
        """清空报文历史记录"""
        self.message_formatter.clear_messages()

    # ===== 日志 =====

    @property
    def log(self):
        """获取设备日志器（延迟初始化）
        
        使用 loguru 的 bind() 模式，每个设备有独立的日志上下文。
        日志文件自动路由到 log/{device_name}/{device_name}.log
        """
        if self._logger is None:
            device_name = self.name or "unknown_device"
            self._logger = get_device_logger(
                device_name, auto_register=self._logger_initialized
            )
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

    # ===== 事件处理（委托给 PointOperator） =====

    def on_point_value_changed(self, sender: Any, **extra: Any) -> None:
        """处理测点值变化事件"""
        self.point_operator.on_point_value_changed(sender, **extra)

    def setRelatedPoint(
        self, point: BasePoint, related_point: BasePoint
    ) -> None:
        """设置测点关联"""
        self.point_operator.set_related_point(point, related_point)
