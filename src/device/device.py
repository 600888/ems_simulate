import os
import time
import asyncio
from typing import Any, Literal, Union, Optional, Dict, List
import c104
from dlt645.service.serversvc.server_service import (
    MeterServerService,
)

from src.config.global_config import ROOT_DIR
from src.config.log.logger import Log
from src.config.plan import Plan
from src.data.data_importer import DataImporter
from src.data.service.point_service import PointService
from src.device.data_update.data_update_thread import DataUpdateThread
from src.device.simulator.simulation_controller import SimulationController
from src.enums.point_data import SimulateMethod, Yc, Yx, DeviceType
from src.enums.modbus_def import ProtocolType
from src.proto.pyModbus.client import ModbusClient
from src.proto.pyModbus.server import ModbusServer
from src.proto.iec104.iec104client import IEC104Client
from src.proto.iec104.iec104server import IEC104Server
from src.tools.export_point import PointExporter
from src.tools.import_point import PointImporter


class Device:
    def __init__(self) -> None:
        """初始化设备实例"""
        self.device_id: int = 0
        self.name: str = ""
        self.codeToDataPointMap: Dict[str, Optional[Union[Yc, Yx]]] = {}
        self.addressDict: Dict = {}
        self.yc_dict: Dict[int, List[Yc]] = {}
        self.yx_dict: Dict[int, List[Yx]] = {}
        self.plan_point_list: List[Union[Yc, Yx]] = []
        self.ip: str = "0.0.0.0"
        self.port: int = 0
        self.serial_port: int = 0
        self.server: Optional[Union[ModbusServer, IEC104Server, MeterServerService]] = (
            None
        )
        self.client: Optional[Union[IEC104Client, ModbusClient]] = None
        self.meter_address: str = "000000000000"
        self.slave_cnt: int = 1
        self.simulation_controller: SimulationController = SimulationController(self)
        self.plan: Optional[Plan] = None
        self.log: Optional[Log] = None
        self.device_type: DeviceType = DeviceType.Other
        self.protocol_type: ProtocolType = ProtocolType.ModbusTcp
        self.slave_id_list: List = []  # 存放从机id列表

        # 初始化相关组件
        self.init_point_dict()
        self.data_update_thread: DataUpdateThread = DataUpdateThread(
            task=self.update_data
        )

    def update_data(self) -> None:
        """更新设备数据"""
        for slave_id in self.slave_id_list:
            # 获取原始数据（保持原有逻辑）
            yc_list: List[Yc] = self.yc_dict.get(slave_id, [])
            yx_list: List[Yx] = self.yx_dict.get(slave_id, [])
            self.getSlaveRegisterValues(yc_list, yx_list)
        # 每隔1秒刷新数据
        time.sleep(1)

    def setAllPointSimulateMethod(self, simulate_method: str) -> None:
        """设置所有点的模拟方法

        Args:
            simulate_method: 模拟方法字符串
        """
        simulate_method_enum: Optional[SimulateMethod] = None

        if simulate_method == SimulateMethod.Random.value:
            simulate_method_enum = SimulateMethod.Random
        elif simulate_method == SimulateMethod.AutoIncrement.value:
            simulate_method_enum = SimulateMethod.AutoIncrement
        elif simulate_method == SimulateMethod.AutoDecrement.value:
            simulate_method_enum = SimulateMethod.AutoDecrement
        elif simulate_method == SimulateMethod.SineWave.value:
            simulate_method_enum = SimulateMethod.SineWave
        elif simulate_method == SimulateMethod.Ramp.value:
            simulate_method_enum = SimulateMethod.Ramp
        elif simulate_method == SimulateMethod.Pulse.value:
            simulate_method_enum = SimulateMethod.Pulse

        if simulate_method_enum:
            self.simulation_controller.set_all_point_simulate_method(
                simulate_method_enum
            )

    def setSinglePointSimulateMethod(
        self, point_code: str, simulate_method: str
    ) -> bool:
        """设置单个点的模拟方法

        Args:
            point_code: 点的编码
            simulate_method: 模拟方法字符串

        Returns:
            bool: 设置是否成功
        """
        if simulate_method == SimulateMethod.Random.value:
            return self.simulation_controller.set_single_point_simulate_method(
                point_code, SimulateMethod.Random
            )
        elif simulate_method == SimulateMethod.AutoIncrement.value:
            return self.simulation_controller.set_single_point_simulate_method(
                point_code, SimulateMethod.AutoIncrement
            )
        elif simulate_method == SimulateMethod.AutoDecrement.value:
            return self.simulation_controller.set_single_point_simulate_method(
                point_code, SimulateMethod.AutoDecrement
            )
        elif simulate_method == SimulateMethod.SineWave.value:
            return self.simulation_controller.set_single_point_simulate_method(
                point_code, SimulateMethod.SineWave
            )
        elif simulate_method == SimulateMethod.Ramp.value:
            return self.simulation_controller.set_single_point_simulate_method(
                point_code, SimulateMethod.Ramp
            )
        elif simulate_method == SimulateMethod.Pulse.value:
            return self.simulation_controller.set_single_point_simulate_method(
                point_code, SimulateMethod.Pulse
            )
        return False

    def setSinglePointStep(self, point_code: str, step: int) -> bool:
        """设置单个点的模拟步长

        Args:
            point_code: 点的编码
            step: 模拟步长值

        Returns:
            bool: 设置是否成功
        """
        return self.simulation_controller.set_single_point_step(point_code, step)

    def getPointInfo(self, point_code: str) -> Dict:
        """获取单个点的信息

        Args:
            point_code: 点的编码

        Returns:
            Dict: 包含点信息的字典
        """
        return self.simulation_controller.get_point_info(point_code)

    def setPointSimulationRange(
        self, point_code: str, min_value: float, max_value: float
    ) -> bool:
        """设置单个点的模拟范围

        Args:
            point_code: 点的编码
            min_value: 最小值
            max_value: 最大值

        Returns:
            bool: 设置是否成功
        """
        return self.simulation_controller.set_point_simulation_range(
            point_code, min_value, max_value
        )

    def startSimulation(self) -> None:
        """启动模拟"""
        self.simulation_controller.start_simulation()

    def stopSimulation(self) -> None:
        """停止模拟"""
        self.simulation_controller.stop_simulation()

    def isSimulationRunning(self) -> bool:
        """检查模拟是否正在运行

        Returns:
            bool: 模拟是否正在运行
        """
        return self.simulation_controller.is_simulation_running()

    def initSimulationPointList(self) -> None:
        """初始化模拟点列表"""
        for point_list in self.yc_dict.values():
            for point in point_list:
                self.simulation_controller.add_point(point, SimulateMethod.Random, 1)
                self.simulation_controller.set_point_status(point, True)
        for point_list in self.yx_dict.values():
            for point in point_list:
                self.simulation_controller.add_point(point, SimulateMethod.Random, 1)
                self.simulation_controller.set_point_status(point, True)

    def initLog(self) -> None:
        """初始化日志系统"""
        # 确保日志目录存在
        log_dir: str = os.path.join(ROOT_DIR, "log", self.name)
        os.makedirs(log_dir, exist_ok=True)

        self.log = Log(
            filename=os.path.join(log_dir, f"{self.name}.log"),
            cmdlevel="INFO",
            filelevel="INFO",
            limit=1024000,
            backup_count=1,
            colorful=True,
        )

    def initModbusTcpClient(self, ip: str, port: int) -> None:
        """初始化Modbus TCP客户端"""
        self.protocol_type = ProtocolType.ModbusTcpClient
        self.client = ModbusClient(ip, port, log=self.log)

    def initModbusTcpServer(
        self, port: int, protocol_type: ProtocolType = ProtocolType.ModbusTcp
    ) -> None:
        """初始化Modbus TCP服务器

        Args:
            port: 服务器端口
            protocol_type: 协议类型，默认为Modbus TCP
        """
        self.protocol_type = protocol_type
        self.server = ModbusServer(self.log, self.slave_id_list, port, protocol_type)

    def initModbusSerialServer(self) -> None:
        """初始化Modbus串口服务器

        注意：目前该功能尚未完全开发，因为串口测试较少
        """
        self.protocol_type = ProtocolType.ModbusRtu
        self.server = ModbusServer(
            self.log, self.slave_id_list, self.port, ProtocolType.ModbusRtu
        )
        # TODO: 串口功能尚未完全开发，需要完善配置和初始化逻辑

    def initIec104Client(self) -> None:
        """初始化IEC104客户端

        Raises:
            Exception: 初始化失败时抛出异常
        """
        try:
            self.protocol_type = ProtocolType.Iec104Client
            self.client = IEC104Client(ip=self.ip, port=self.port, common_address=1)

            # 添加遥测和遥调点
            self._add_iec104_client_points()
        except Exception as e:
            if self.log:
                self.log.error(f"初始化IEC104客户端失败: {e}")
            raise e

    def _add_iec104_client_points(self) -> None:
        """为IEC104客户端添加各种类型的点"""
        # 添加遥测和遥调点
        for point_list in self.yc_dict.values():
            for point in point_list:
                if point.frame_type == 0:
                    self.client.add_point(
                        io_address=point.address,
                        point_type=c104.Type.M_ME_NC_1,  # 默认短浮点数
                    )
                elif point.frame_type == 3:
                    self.client.add_point(
                        io_address=point.address,
                        point_type=c104.Type.C_SE_NC_1,  # 默认单点遥调浮点数
                    )

        # 添加遥信和遥控点
        for point_list in self.yx_dict.values():
            for point in point_list:
                if point.frame_type == 1:
                    self.client.add_point(
                        io_address=point.address,
                        point_type=c104.Type.M_SP_NA_1,  # 默认单点遥信
                    )
                elif point.frame_type == 2:
                    self.client.add_point(
                        io_address=point.address,
                        point_type=c104.Type.C_SC_NA_1,  # 默认单点遥控
                    )

    def _add_iec104_server_points(self) -> None:
        """为IEC104服务器添加各种类型的点"""
        # 添加监控点和命令点
        for point_list in self.yc_dict.values():
            for point in point_list:
                if point.frame_type == 0:
                    self.server.add_monitoring_point(
                        io_address=point.address,
                        point_type=c104.Type.M_ME_NC_1,  # 默认短浮点数
                    )
                elif point.frame_type == 3:
                    self.server.add_command_point(
                        io_address=point.address,
                        point_type=c104.Type.C_SE_NC_1,  # 默认单点遥调浮点数
                    )

        for point_list in self.yx_dict.values():
            for point in point_list:
                if point.frame_type == 1:
                    self.server.add_monitoring_point(
                        io_address=point.address,
                        point_type=c104.Type.M_SP_NA_1,  # 默认单点遥信
                    )
                elif point.frame_type == 2:
                    self.server.add_command_point(
                        io_address=point.address,
                        point_type=c104.Type.C_SC_NA_1,  # 默认单点遥控
                    )

    def initIec104Server(self) -> None:
        """初始化IEC104服务器

        Raises:
            Exception: 初始化失败时抛出异常
        """
        try:
            self.protocol_type = ProtocolType.Iec104Server
            self.server = IEC104Server(ip="0.0.0.0", port=self.port, common_address=1)

            # 添加所有监控点和命令点
            self._add_iec104_server_points()
        except Exception as e:
            if self.log:
                self.log.error(f"初始化IEC104服务器失败: {e}")
            raise e

    async def start(self) -> bool:
        """启动设备

        Returns:
            bool: 启动是否成功
        """
        try:
            if self.protocol_type == ProtocolType.Iec104Client:
                if self.client:
                    self.client.connect()
                    return True
            elif self.protocol_type == ProtocolType.Dlt645Server:
                if (
                    self.server
                    and hasattr(self.server, "server")
                    and hasattr(self.server.server, "start")
                ):
                    self.server.server.start()
                    return True
            elif self.protocol_type == ProtocolType.ModbusTcpClient:
                if self.client:
                    self.client.connect()
                    return True
            elif (
                self.protocol_type == ProtocolType.ModbusTcp
                or self.protocol_type == ProtocolType.Iec104Server
            ):
                if self.server and hasattr(self.server, "start"):
                    # 对于Modbus TCP服务器，使用asyncio.create_task在后台启动，避免阻塞
                    if self.protocol_type == ProtocolType.ModbusTcp:
                        asyncio.create_task(self.server.start())
                    else:
                        self.server.start()
                    return True
            return False
        except Exception as e:
            if self.log:
                self.log.error(f"启动设备失败: {e}")
            return False

    async def stop(self) -> bool:
        """停止设备

        Returns:
            bool: 停止是否成功
        """
        try:
            print(f"尝试停止设备: {self.protocol_type}")
            if self.protocol_type == ProtocolType.Iec104Client:
                if self.client:
                    self.client.disconnect()
                    return True
            elif self.protocol_type == ProtocolType.Dlt645Server:
                if (
                    self.server
                    and hasattr(self.server, "server")
                    and hasattr(self.server.server, "stop")
                ):
                    self.server.server.stop()
                    return True
            elif self.protocol_type == ProtocolType.ModbusTcpClient:
                if self.client:
                    self.client.disconnect()
                    return True
            elif (
                self.protocol_type == ProtocolType.ModbusTcp
                or self.protocol_type == ProtocolType.Iec104Server
            ):
                if self.server and hasattr(self.server, "stop"):
                    # 根据服务器类型选择同步或异步停止方法
                    if self.protocol_type == ProtocolType.ModbusTcp:
                        await self.server.stopAsync()
                    else:
                        self.server.stop()
                    return True
            return False
        except Exception as e:
            print(f"停止设备失败: {e}")
            if self.log:
                self.log.error(f"停止设备失败: {e}")
            return False

    def initDlt645Server(self) -> None:
        """初始化DLT645 TCP服务器

        Raises:
            Exception: 初始化失败时抛出异常
        """
        try:
            self.protocol_type = ProtocolType.Dlt645Server
            self.server = MeterServerService.new_tcp_server(
                ip="0.0.0.0", port=self.port, timeout=30
            )

            # 设置设备地址，使用已有的meter_address
            self.server.set_address(self.meter_address)
            self.server.server.start()

            if self.log:
                self.log.info(
                    f"初始化DLT645 TCP服务器成功, IP: {self.ip}, Port: {self.port}"
                )
                self.log.info(f"设备地址: {self.meter_address}")

        except Exception as e:
            if self.log:
                self.log.error(f"初始化DLT645服务器失败: {e}")
            raise e

    def setSpecialDataPointValues(self) -> None:
        """设置特殊数据点的值

        注意：当前方法为占位实现，需要根据具体业务需求进行完善
        """
        pass

    def initPointValues(self) -> None:
        """初始化点的值

        注意：当前方法为占位实现，需要根据具体业务需求进行完善
        """

    def resetPointValues(self) -> None:
        """将所有测点值重置为默认值（通常为0）"""
        # 重置所有点的值为0
        for point_code in self.codeToDataPointMap:
            self.editPointData(point_code, 0)
        # 调用初始化方法进一步处理
        self.initPointValues()

    def init_point_dict(self) -> None:
        """初始化点字典，为每个可能的从机ID创建空的遥测和遥信列表

        初始化范围为0-254（共255个可能的从机ID）
        """
        for slave_id in range(0, 255):
            self.yc_dict[slave_id] = []
            self.yx_dict[slave_id] = []

    def set_device_id(self, device_id: int) -> None:
        """设置设备ID

        Args:
            device_id: 设备的唯一标识符
        """
        self.device_id = device_id

    def set_name(self, name: str) -> None:
        """设置设备名称

        Args:
            name: 设备的名称字符串
        """

    @staticmethod
    def frame_type_dict() -> Dict[int, str]:
        """获取帧类型字典，用于将帧类型数值映射为可读的中文名称

        Returns:
            Dict[int, str]: 帧类型数值到中文名称的映射字典
        """
        return {
            0: "遥测",
            1: "遥信",
            2: "遥控",
            3: "遥调",
        }

    @staticmethod
    def set_frame_type(is_yc: bool, func_code: int) -> int:
        """根据点类型和功能码确定帧类型

        Args:
            is_yc: 是否为遥测点
            func_code: 功能码

        Returns:
            int: 帧类型数值（0-3）
        """
        # 常见功能码（1-4）和特殊功能码的处理逻辑分离
        is_common_func: bool = func_code in [1, 2, 3, 4]

        if is_yc:
            return 0 if is_common_func else 3
        else:
            return 1 if is_common_func else 2

    @staticmethod
    def get_value_by_bit(value: int, bit: int) -> int:
        """获取整数中指定位的值

        Args:
            value: 要提取位值的整数
            bit: 要获取的位位置（从0开始计数）

        Returns:
            int: 指定位的值（0或1）
        """
        return (value >> bit) & 1

    def importDataPointFromDb(
        self, grp_code: str, protocol_type: ProtocolType = ProtocolType.ModbusTcp
    ) -> None:
        """从数据库导入数据点

        Args:
            grp_code: 组编码，用于过滤要导入的数据点
            protocol_type: 协议类型，默认为Modbus TCP
        """
        # 创建数据导入器实例并执行导入
        data_importer: DataImporter = DataImporter(device=self)
        data_importer.importData(grp_code, protocol_type)

        # 导入后初始化相关组件
        self.initSimulationPointList()
        self.initLog()

    def importDataPointFromCsv(self, file_name: str) -> None:
        """从CSV文件导入数据点

        Args:
            file_name: CSV文件路径
        """
        # 创建CSV导入器实例并执行导入
        point_importer: PointImporter = PointImporter(device=self, file_name=file_name)
        point_importer.importDataPointCsv()

        # 导入后初始化相关组件
        self.initSimulationPointList()
        self.initLog()

    def exportDataPointCsv(self, file_path: str) -> None:
        """将数据点导出到CSV文件

        Args:
            file_path: 导出的CSV文件路径
        """
        # 创建CSV导出器实例并执行导出
        point_exporter: PointExporter = PointExporter(device=self, file_path=file_path)
        point_exporter.exportDataPointCsv(file_path)

    def get_table_head(self) -> List[str]:
        """获取表格头部列名

        Returns:
            List[str]: 包含所有列名的列表
        """
        return [
            "地址",
            "16进制地址",
            "位",
            "功能码",
            "解析码",
            "测点名称",
            "测点编码",
            "寄存器值",
            "真实值",
            "乘法系数",
            "加法系数",
            "帧类型",
        ]

    def get_table_data(
        self,
        slave_id: int,
        name: Optional[str] = None,
        page_index: Optional[int] = 1,
        page_size: Optional[int] = 1,
        point_types: Optional[List[int]] = [0, 1, 2, 3],
    ) -> tuple[List[List[str]], int]:
        """获取表格数据，支持分页和筛选

        Args:
            slave_id: 从机ID
            name: 名称筛选关键词，默认为None
            page_index: 当前页码，默认为1
            page_size: 每页记录数，默认为1
            point_types: 点类型列表，默认为[0,1,2,3]

        Returns:
            tuple[List[List[str]], int]: 表格数据和总记录数
        """
        # 确保point_types不为空
        if point_types is None or not point_types:
            point_types = [0, 1, 2, 3]

        # 获取原始数据并更新
        yc_list: List[Yc] = self.yc_dict.get(slave_id, [])
        yx_list: List[Yx] = self.yx_dict.get(slave_id, [])
        self.getSlaveRegisterValues(yc_list, yx_list)

        # 合并并过滤数据
        table_data: list[Any] = []
        frame_type_dict: Dict[int, str] = self.frame_type_dict()

        # 处理YC数据
        for yc in yc_list:
            if (
                name is None or str(yc.name).find(name) != -1
            ) and yc.frame_type in point_types:  # type: ignore
                table_data.append(
                    [
                        str(yc.address),
                        str(yc.hex_address),
                        "",
                        str(yc.func_code),
                        str(yc.decode),
                        str(yc.name),
                        str(yc.code),
                        str(yc.hex_value),
                        str(yc.real_value),
                        str(yc.mul_coe),
                        str(yc.add_coe),
                        str(frame_type_dict[yc.frame_type]),
                    ]
                )

        # 处理YX数据
        for yx in yx_list:
            if (
                name is None or str(yx.name).find(name) != -1
            ) and yx.frame_type in point_types:  # type: ignore
                table_data.append(
                    [
                        str(yx.address),
                        str(yx.hex_address),
                        str(yx.bit),
                        str(yx.func_code),
                        str(yx.decode),
                        str(yx.name),
                        str(yx.code),
                        str(yx.hex_value),
                        str(int(yx.value)),
                        "1.0",
                        "0",
                        str(frame_type_dict[yx.frame_type]),
                    ]
                )

        total = len(table_data)
        if page_index is None or page_size is None:
            return table_data, total
        else:
            # 分页处理
            start: int = (page_index - 1) * page_size
            end: int = start + page_size
            paginated_data: list[Any] = table_data[start:end]
            return paginated_data, total

    def exportDataPointXlsx(self, file_path: str) -> None:
        """将数据点导出到Excel XLSX文件

        Args:
            file_path: 导出的Excel文件路径
        """
        # 创建Excel导出器实例并执行导出
        point_exporter: PointExporter = PointExporter(device=self, file_path=file_path)
        point_exporter.exportDataPointXlsx(file_path)

    def getRegisterValueByBit(
        self, func_code: int, slave_id: int, address: int, bit: int
    ) -> Any | Literal[0]:
        """获取寄存器中特定位的值

        Args:
            func_code: 功能码
            slave_id: 从机ID
            address: 寄存器地址
            bit: 要获取的位位置（从0开始计数）

        Returns:
            Any | Literal[0]: 位值（通常是0或1），如果服务器类型不支持则返回0
        """
        if isinstance(self.server, ModbusServer):
            # 先从寄存器中取出值
            register_value: Any | Literal[0] = self.server.getValueByAddress(
                func_code, slave_id, address
            )
            # 根据bit位取值
            value = (register_value >> bit) & 1
            return value
        else:
            # 对于非 ModbusServer 类型，返回默认值 0
            return 0

    def setRegisterValueByBit(
        self, func_code: int, slave_id: int, address: int, bit: int, value: int
    ) -> None:
        """设置寄存器中特定位的值

        Args:
            func_code: 功能码
            slave_id: 从机ID
            address: 寄存器地址
            bit: 要设置的位位置（从0开始计数）
            value: 要设置的值（0或非0值）
        """
        if isinstance(self.server, ModbusServer):
            # 先从寄存器中取出值
            register_value = self.server.getValueByAddress(func_code, slave_id, address)
            # 根据bit位修改值
            if value > 0:
                register_value = register_value | (1 << bit)
            else:
                register_value = register_value & ~(1 << bit)
            # 写入寄存器
            self.server.setValueByAddress(func_code, slave_id, address, register_value)
        elif isinstance(self.client, ModbusClient):
            # 先读取寄存器中的值
            register_value = self.client.read_value_by_address(
                func_code, slave_id, address
            )
            # 根据bit位修改值
            if value > 0:
                register_value = register_value | (1 << bit)
            else:
                register_value = register_value & ~(1 << bit)
            # 写入寄存器
            self.client.write_value_by_address(
                func_code, slave_id, address, register_value
            )

    def getSlaveValueList(
        self, slave_id: int, point_name: str = ""
    ) -> tuple[List[Any], List[str], List[float], List[int], List[int]]:
        """获取指定从机的测点值、十六进制值、真实值及上下限值

        Args:
            slave_id: 从机ID
            point_name: 点名称筛选关键词，默认为空字符串（表示不筛选）

        Returns:
            tuple[List[Any], List[str], List[float], List[int], List[int]]:
                - 数据值列表
                - 十六进制值列表
                - 真实值列表（保留2位小数）
                - 上限值列表
                - 下限值列表
        """
        yc_list = self.yc_dict.get(slave_id, [])
        yx_list = self.yx_dict.get(slave_id, [])
        # 将寄存器的值赋给测点
        self.getSlaveRegisterValues(yc_list, yx_list)

        # 初始化返回数据列表
        data_list: List[Any] = []
        hex_data_list: List[str] = []
        real_data_list: List[float] = []
        max_limit_list: List[int] = []
        min_limit_list: List[int] = []

        # 处理YC数据
        for yc in yc_list:
            if not point_name or point_name in yc.name:
                data_list.append(yc.value)
                hex_data_list.append(yc.hex_value)
                real_data_list.append(round(yc.real_value, 2))
                max_limit_list.append(yc.max_value_limit)
                min_limit_list.append(yc.min_value_limit)

        # 处理YX数据
        for yx in yx_list:
            if not point_name or point_name in yx.name:
                data_list.append(yx.value)
                hex_data_list.append(yx.hex_value)
                real_data_list.append(yx.value)
                max_limit_list.append(1)  # YX类型默认上限为1
                min_limit_list.append(0)  # YX类型默认下限为0

        return data_list, hex_data_list, real_data_list, max_limit_list, min_limit_list

    def getSlaveRegisterValues(self, yc_list: List[Yc], yx_list: List[Yx]) -> None:
        """从服务器获取寄存器值并更新到YC和YX点对象中

        Args:
            yc_list: YC类型点列表
            yx_list: YX类型点列表
        """

        def setPointValue(point: Union[Yc, Yx]) -> None:
            if isinstance(self.server, ModbusServer) or isinstance(
                self.client, ModbusClient
            ):
                # 对于 Yx 类型，检查是否有 bit 属性并且不为空
                if (
                    isinstance(point, Yx)
                    and hasattr(point, "bit")
                    and point.bit is not None
                    and point.bit != ""
                ):
                    value = self.getRegisterValueByBit(
                        point.func_code, point.rtu_addr, point.address, point.bit
                    )
                    # 确保返回值不为 None，如果为 None 则设为 0
                    point.value = value if value is not None else 0
                else:
                    # 对于 Yc 类型或没有 bit 属性的 Yx 类型
                    register_cnt = getattr(point, "register_cnt", 1)  # 默认为1
                    is_signed = getattr(point, "is_signed", False)  # 默认为False
                    if isinstance(self.server, ModbusServer):
                        value = self.server.getValueByAddress(
                            func_code=point.func_code,
                            rtu_addr=point.rtu_addr,
                            address=point.address,
                            decode=point.decode,
                            signed=is_signed,
                            register_cnt=register_cnt,
                        )
                    elif isinstance(self.client, ModbusClient):
                        value = self.client.read_value_by_address(
                            func_code=point.func_code,
                            slave_id=point.rtu_addr,
                            address=point.address,
                            decode=point.decode,
                            signed=is_signed,
                            register_cnt=register_cnt,
                        )
                    # 确保返回值不为 None，如果为 None 则设为 0
                    point.value = value if value is not None else 0
            elif isinstance(self.server, IEC104Server):
                value = self.server.get_point_value(
                    io_address=point.address, frame_type=point.frame_type
                )
                # 确保返回值不为 None，如果为 None 则设为 0
                point.value = value if value is not None else 0
            elif isinstance(self.client, IEC104Client):
                value = self.client.read_point(
                    io_address=point.address, frame_type=point.frame_type
                )
                # 确保返回值不为 None，如果为 None 则设为 0
                point.value = value if value is not None else 0
            elif isinstance(self.server, MeterServerService):
                data_item = self.server.get_data_item(di=point.address)
                if data_item is not None:
                    point.value = data_item.value
                else:
                    point.value = 0

        # 将寄存器的值映射到测点中
        for i in range(0, len(yc_list)):
            setPointValue(yc_list[i])
        for i in range(0, len(yx_list)):
            setPointValue(yx_list[i])

    def editPointData(self, point_code: str, real_value: float) -> bool:
        """编辑指定测点的真实值数据

        Args:
            point_code: 测点编码
            real_value: 要设置的真实值

        Returns:
            bool: 设置是否成功

        Raises:
            Exception: 如果设置过程中发生错误
        """
        try:
            if point_code not in self.codeToDataPointMap:
                if self.log:
                    self.log.error(f"{self.name}未找到对应的测点: {point_code}!")
                return False

            point = self.codeToDataPointMap[point_code]
            if point is None or not point.set_real_value(real_value):
                return False

            if isinstance(self.server, ModbusServer) or isinstance(
                self.client, ModbusClient
            ):
                # 对于 Yx 类型，检查是否有 bit 属性并且不为空
                if (
                    isinstance(point, Yx)
                    and hasattr(point, "bit")
                    and point.bit is not None
                    and point.bit != ""
                ):
                    self.setRegisterValueByBit(
                        func_code=point.func_code,
                        slave_id=point.rtu_addr,
                        address=point.address,
                        bit=point.bit,
                        value=point.value,
                    )
                else:
                    # 对于 Yc 类型或没有 bit 属性的 Yx 类型
                    register_cnt = getattr(point, "register_cnt", 1)  # 默认为1
                    is_signed = getattr(point, "is_signed", False)  # 默认为False
                    if isinstance(self.server, ModbusServer):
                        self.server.setValueByAddress(
                            func_code=point.func_code,
                            rtu_addr=point.rtu_addr,
                            address=point.address,
                            value=point.value,
                            decode=point.decode,
                            signed=is_signed,
                            register_cnt=register_cnt,
                        )
                    else:
                        self.client.write_value_by_address(
                            func_code=point.func_code,
                            slave_id=point.rtu_addr,
                            address=point.address,
                            value=point.value,
                            decode=point.decode,
                            signed=is_signed,
                            register_cnt=register_cnt,
                        )
            elif isinstance(self.server, IEC104Server):
                self.server.set_point_value(
                    io_address=point.address,
                    value=point.value,
                    frame_type=point.frame_type,
                )
            elif isinstance(self.client, IEC104Client):
                self.client.write_point(
                    io_address=point.address,
                    value=point.value,
                    frame_type=point.frame_type,
                )
            elif isinstance(self.server, MeterServerService):
                di = point.address
                data_item = self.server.get_data_item(di=di)
                if data_item is not None:
                    data_item.value = point.value

            return True
        except Exception as e:
            if self.log:
                self.log.error(f"编辑测点数据失败: {e}")
            raise e

    def edit_point_limit(
        self, point_code: str, min_value_limit: int, max_value_limit: int
    ) -> bool:
        """编辑指定测点的上下限数值

        Args:
            point_code: 测点编码
            min_value_limit: 下限值
            max_value_limit: 上限值

        Returns:
            bool: 设置是否成功
        """
        if point_code not in self.codeToDataPointMap:
            if self.log:
                self.log.error(f"{self.name}未找到对应的测点: {point_code}!")
            return False

        point = self.codeToDataPointMap[point_code]
        if point is None:
            return False

        # 只为 Yc 类型设置限制值，因为 Yx 没有这些属性
        if isinstance(point, Yc):
            point.min_value_limit = min_value_limit
            point.max_value_limit = max_value_limit
            return PointService.update_point_limit(
                self.name, point_code, min_value_limit, max_value_limit
            )
        return True

    def get_point_data(self, point_code_list: List[str]) -> Optional[Union[Yc, Yx]]:
        """获取指定点编码列表中第一个存在的测点数据

        Args:
            point_code_list: 点编码列表

        Returns:
            Optional[Union[Yc, Yx]]: 找到的第一个测点对象，如果没有找到则返回None
        """
        for point_code in point_code_list:
            if point_code in self.codeToDataPointMap:
                return self.codeToDataPointMap[point_code]
        return None

    def on_point_value_changed(self, sender: Any, **extra: Any) -> None:
        """处理测点值变化事件，并更新关联测点的值

        Args:
            sender: 发送事件的对象
            **extra: 额外参数，包含old_point和related_point
        """
        old_point: Optional[Union[Yc, Yx]] = extra.get("old_point")
        related_point: Optional[Union[Yc, Yx]] = extra.get("related_point")

        # 参数有效性检查
        if old_point is None:
            if self.log:
                self.log.error("未找到测点!")
            return

        if related_point is None:
            if self.log:
                self.log.error("未找到关联的测点!")
            return

        try:
            # 判断是否使用关联值
            if old_point.related_value is None:
                # 直接使用原值
                if isinstance(old_point, Yx):
                    change_value = old_point.value
                else:
                    change_value = old_point.real_value

                # 更新关联点值
                self.editPointData(related_point.code, change_value)

                if self.log:
                    self.log.info(
                        f"point value changed, old_point: {old_point.code}, related_point: {related_point.code}, "
                        f"old_value: {related_point.value}, new_value: {change_value}"
                    )
            else:
                # 使用关联映射值
                if isinstance(old_point, Yx):
                    relate_value = old_point.related_value.get(old_point.value)
                else:
                    relate_value = old_point.related_value.get(
                        int(old_point.real_value)
                    )

                # 检查关联值是否存在
                if relate_value is None:
                    if self.log:
                        self.log.error(
                            f"未找到关联值, point: {old_point.code}, related_point: {related_point.code}, "
                            f"old_value: {old_point.value}"
                        )
                    return

                # 更新关联点值
                self.editPointData(related_point.code, relate_value)

                if self.log:
                    self.log.info(
                        f"use related value, point value changed, old_point: {old_point.code}, related_point: {related_point.code}, "
                        f"old_value: {related_point.value}, new_value: {relate_value}"
                    )
        except Exception as e:
            if self.log:
                self.log.error(f"处理点值变化事件时发生错误: {e}")

    def setRelatedPoint(
        self, point: Union[Yc, Yx], related_point: Union[Yc, Yx]
    ) -> None:
        """设置两个测点之间的关联关系

        Args:
            point: 源测点（触发变化的点）
            related_point: 目标关联测点（被更新的点）
        """
        # 参数有效性检查
        if point is None or related_point is None:
            if self.log:
                self.log.warning("尝试设置关联关系时传入了None值")
            return

        # 检查点是否在设备的点映射表中
        if (
            point.code not in self.codeToDataPointMap
            or related_point.code not in self.codeToDataPointMap
        ):
            if self.log:
                self.log.warning(
                    f"点{point.code}或{related_point.code}不在设备的点映射表中"
                )
            return

        # 设置关联关系并启用信号发送
        try:
            # 使用 setattr 来避免类型检查问题
            setattr(point, "related_point", related_point)
            point.is_send_signal = True
            point.value_changed.connect(self.on_point_value_changed)

            if self.log:
                self.log.info(f"已设置点{point.code}与点{related_point.code}的关联关系")
        except Exception as e:
            if self.log:
                self.log.error(f"设置点关联关系时发生错误: {e}")
