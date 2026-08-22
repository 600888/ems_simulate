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

import asyncio
import time
from typing import Any

from src.config.log.device_logger import DeviceLoggerManager, get_device_logger
from src.device.core.data.data_exporter import DataExporter
from src.device.core.data.data_reader import DataReader
from src.device.core.message.message_formatter import MessageFormatter
from src.device.core.point.point_calculator import PointCalculator
from src.device.core.point.point_manager import PointManager
from src.device.core.point.point_operator import PointOperator
from src.device.core.slave_manager import SlaveManager
from src.device.data_update.data_update_thread import DataUpdateThread

# 协议处理器延迟导入，减少启动时间
from src.device.protocol import ProtocolHandler
from src.device.protocol.base_handler import ClientHandler
from src.device.protocol.dlt645_handler import DLT645ClientHandler, DLT645ServerHandler
from src.device.protocol.dnp3_handler import DNP3ClientHandler, DNP3ServerHandler
from src.device.protocol.iec104_handler import IEC104ClientHandler, IEC104ServerHandler
from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler
from src.device.protocol.modbus_handler import ModbusClientHandler, ModbusServerHandler
from src.device.simulator.simulation_controller import SimulationController
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import BasePoint, DeviceType, SimulateMethod, Yc, Yk, Yt, Yx
from src.enums.points.change_tracker import ChangeSource


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
        self.serial_port: str | None = None  # 串口号（用于RTU模式）
        self.baudrate: int = 9600
        self.databits: int = 8
        self.stopbits: int = 1
        self.parity: str = "E"
        self.meter_address: str = "000000000000"
        self.device_type: DeviceType = DeviceType.Other
        self.protocol_type: ProtocolType = protocol_type
        self.model_name: str | None = None  # IED 模型名称 (IEC61850)
        self.icd_path: str | None = None  # ICD 文件存储路径 (IEC61850, v2.0)

        # 核心组件
        self.runtime_config: dict[str, Any] = {}
        self.security_config: dict[str, Any] = {
            "tls_enabled": False,
            "tls_mode": "one_way",
            "certificate_path": None,
            "private_key_path": None,
            "ca_certificate_path": None,
        }

        self.point_manager: PointManager = PointManager()
        self.protocol_handler: ProtocolHandler | None = None
        self.data_exporter: DataExporter = DataExporter(self.point_manager)

        # 功能组件（持有 self 引用，始终跟踪最新状态）
        self.data_reader: DataReader = DataReader(self)
        self.point_operator: PointOperator = PointOperator(self)
        self.slave_manager: SlaveManager = SlaveManager(self)
        self.message_formatter: MessageFormatter = MessageFormatter(self)

        # 测点计算器
        self.point_calculator: PointCalculator = PointCalculator(self)

        # 仿真控制器
        self.simulation_controller: SimulationController = SimulationController(self)

        # 日志（延迟初始化，在 set_name 或 initLog 时创建）
        self._logger = None
        self._logger_initialized = False

        # 其他
        self.plan: Any | None = None
        self.data_update_thread: DataUpdateThread = DataUpdateThread(task=self.update_data)

    # ===== 只读属性 =====
    @property
    def yc_dict(self) -> dict[int, list[Yc]]:
        """获取遥测字典"""
        return self.point_manager.yc_dict

    @property
    def yx_dict(self) -> dict[int, list[Yx]]:
        """获取遥信字典"""
        return self.point_manager.yx_dict

    @property
    def slave_id_list(self) -> list[int]:
        """获取从机 ID 列表"""
        return self.point_manager.slave_id_list

    @property
    def codeToDataPointMap(self) -> dict[str, BasePoint]:
        """获取编码到测点的映射"""
        return self.point_manager.code_map

    @property
    def server(self):
        """获取底层服务器对象"""
        if isinstance(self.protocol_handler, IEC61850ServerHandler):
            return self.protocol_handler.server
        if isinstance(self.protocol_handler, DNP3ServerHandler):
            return self.protocol_handler.server
        return None

    @property
    def client(self):
        """获取底层客户端对象"""
        if isinstance(self.protocol_handler, IEC61850ClientHandler):
            return self.protocol_handler.client
        if isinstance(self.protocol_handler, DNP3ClientHandler):
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
        """根据协议类型创建处理器（延迟导入协议模块）"""
        from src.device.protocol.iec61850_handler import IEC61850ClientHandler, IEC61850ServerHandler

        handler_map = {
            ProtocolType.ModbusTcp: lambda: ModbusServerHandler(self.log),
            ProtocolType.ModbusRtu: lambda: ModbusServerHandler(self.log),
            ProtocolType.ModbusRtuServer: lambda: ModbusServerHandler(self.log),
            ProtocolType.ModbusRtuClient: lambda: ModbusClientHandler(self.log),
            ProtocolType.ModbusRtuOverTcp: lambda: ModbusServerHandler(self.log),
            ProtocolType.ModbusTcpClient: lambda: ModbusClientHandler(self.log),
            ProtocolType.Iec104Server: lambda: IEC104ServerHandler(self.log),
            ProtocolType.Iec104Client: lambda: IEC104ClientHandler(self.log),
            ProtocolType.Dlt645Server: lambda: DLT645ServerHandler(self.log),
            ProtocolType.Dlt645Client: lambda: DLT645ClientHandler(self.log),
            ProtocolType.Iec61850Server: lambda: IEC61850ServerHandler(self.log),
            ProtocolType.Iec61850Client: lambda: IEC61850ClientHandler(self.log),
            ProtocolType.Dnp3Server: lambda: DNP3ServerHandler(self.log),
            ProtocolType.Dnp3Client: lambda: DNP3ClientHandler(self.log),
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
            "model_name": self.model_name,
            "ied_name": self.model_name,  # IEC61850 IED 名称 (与 model_name 相同，对应 ICD 文件的 IED name)
            "icd_path": self.icd_path,  # ICD 文件路径 (IEC61850, v2.0)
            "runtime": dict(self.runtime_config),
            "security": dict(self.security_config),
        }

    def initProtocol(self) -> None:
        """初始化协议处理器"""
        self.protocol_handler = self._create_protocol_handler()
        self.protocol_handler.initialize(self._build_protocol_config())

        # IEC61850 客户端: 注册测点发现回调
        if self.protocol_type == ProtocolType.Iec61850Client and isinstance(
            self.protocol_handler, IEC61850ClientHandler
        ):
            self.protocol_handler.set_on_points_discovered(self._on_iec61850_points_discovered)

        # IEC61850 测点来自 ICD 模型文件或 MMS 在线发现，不从数据库注册测点
        if self.protocol_type in (ProtocolType.Iec61850Server, ProtocolType.Iec61850Client):
            return

        # 添加测点
        all_points = self.point_manager.get_all_points()
        self.protocol_handler.add_points(all_points)

    # 初始化方法
    def initModbusTcpServer(self, port: int, protocol_type: ProtocolType = ProtocolType.ModbusTcp) -> None:
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
        self.protocol_type = ProtocolType.ModbusRtuServer
        self.initProtocol()

    def initModbusSerialClient(self) -> None:
        """初始化 Modbus RTU 客户端（串口主站）"""
        self.protocol_type = ProtocolType.ModbusRtuClient
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

    def initIec61850Server(self) -> None:
        """初始化 IEC 61850 服务器"""
        self.protocol_type = ProtocolType.Iec61850Server
        self.initProtocol()

    def initIec61850Client(self) -> None:
        """初始化 IEC 61850 客户端"""
        self.protocol_type = ProtocolType.Iec61850Client
        self.initProtocol()

    def initDnp3Server(self) -> None:
        """初始化 DNP3 服务端（Outstation）"""
        self.protocol_type = ProtocolType.Dnp3Server
        self.initProtocol()

    def initDnp3Client(self) -> None:
        """初始化 DNP3 客户端（Master）"""
        self.protocol_type = ProtocolType.Dnp3Client
        self.initProtocol()

    def get_iec61850_connect_progress(self) -> dict:
        """获取 IEC61850 客户端连接、发现或 DataSet 批读进度。

        Returns:
            包含阶段、百分比、任务类型、活动状态和统一耗时的进度快照。
            非 IEC61850 客户端返回空 dict
        """
        if self.protocol_type not in (ProtocolType.Iec61850Client, ProtocolType.Iec61850Server):
            return {}
        if not self.protocol_handler:
            return {}
        if isinstance(self.protocol_handler, IEC61850ClientHandler):
            return self.protocol_handler.get_connect_progress()
        return {}

    @property
    def iec61850_model_loaded(self) -> bool:
        """IEC61850 模型是否已加载"""
        if self.protocol_type not in (ProtocolType.Iec61850Client, ProtocolType.Iec61850Server):
            return False
        if not self.protocol_handler:
            return False
        if isinstance(self.protocol_handler, IEC61850ClientHandler):
            return self.protocol_handler.model_loaded
        # 服务端: 检查 server.model_loaded
        if isinstance(self.protocol_handler, IEC61850ServerHandler) and self.protocol_handler.server:
            return self.protocol_handler.server.model_loaded
        return False

    def load_iec61850_model(self, icd_path: str, scl_result: Any = None) -> bool:
        """加载 IEC61850 ICD 模型（不启动设备）

        加载前先清除内存中所有相关的缓存（测点、模拟控制器等），
        然后加载 ICD 模型并注册到 PointManager。

        Args:
            icd_path: ICD 文件路径
            scl_result: 可选，预先解析的 SclImportResult，提供时跳过内部解析步骤

        Returns:
            是否加载成功
        """
        if not self.protocol_handler:
            return False

        # 清除内存缓存
        self._clear_iec61850_cache()

        success = False
        icd_points = None

        if self.protocol_type == ProtocolType.Iec61850Server:
            if isinstance(self.protocol_handler, IEC61850ServerHandler):
                success = self.protocol_handler.load_model(icd_path, scl_result=scl_result)
                if success:
                    icd_points = self.protocol_handler.get_icd_points()
        elif self.protocol_type == ProtocolType.Iec61850Client:
            if isinstance(self.protocol_handler, IEC61850ClientHandler):
                success = self.protocol_handler.load_model_from_icd(icd_path, scl_result=scl_result)
                if success:
                    icd_points = self.protocol_handler.get_icd_points()

        if success and icd_points:
            self._register_icd_points(icd_points)

        return success

    def _clear_iec61850_cache(self) -> None:
        """清除 IEC61850 内存中所有相关缓存

        在加载/导入/发现模型前调用，确保旧数据不会残留。
        """
        slave_id = 1  # IEC61850 默认使用从机地址 1

        # 清除 PointManager 中的测点
        self.point_manager.yc_dict[slave_id] = []
        self.point_manager.yx_dict[slave_id] = []
        self.point_manager.yk_dict[slave_id] = []
        self.point_manager.yt_dict[slave_id] = []
        self.point_manager.code_map.clear()
        self.point_manager.slave_code_index.clear()
        if slave_id in self.point_manager.slave_id_list:
            self.point_manager.slave_id_list.remove(slave_id)

        # 清除 SimulationController 中的模拟点
        self.simulation_controller.points.clear()

        # 清除协议处理器侧的缓存
        if isinstance(self.protocol_handler, IEC61850ClientHandler):
            self.protocol_handler.clear_cache()
        elif isinstance(self.protocol_handler, IEC61850ServerHandler):
            if self.protocol_handler.server:
                self.protocol_handler.server.reset_model()

        self.log.info("IEC61850 内存缓存已清除")

    def _register_icd_points(self, icd_points: dict[str, list]) -> None:
        """将 ICD 解析出的测点注册到 PointManager

        Args:
            icd_points: {"yc_points": [...], "yx_points": [...], "yk_points": [...], "yt_points": [...]}
        """
        slave_id = 1  # IEC61850 默认使用从机地址 1
        added_count = 0

        frame_type_map = {
            "yc_points": 0,
            "yx_points": 1,
            "yk_points": 2,
            "yt_points": 3,
        }

        point_class_map = {
            "yc_points": Yc,
            "yx_points": Yx,
            "yk_points": Yk,
            "yt_points": Yt,
        }

        func_code_map = {
            "yc_points": 3,
            "yx_points": 1,
            "yk_points": 5,
            "yt_points": 6,
        }

        # 使用哈希集 O(1) 查重，避免线性扫描
        seen: set[tuple[int, int]] = set()
        for category_key, ft in frame_type_map.items():
            point_class = point_class_map[category_key]
            func_code = func_code_map[category_key]
            for pd in icd_points.get(category_key, []):
                addr = pd.reg_addr
                # 根据 address + frame_type 去重
                key = (addr, ft)
                if key in seen:
                    continue
                seen.add(key)

                point = point_class(
                    rtu_addr=str(slave_id),
                    address=str(addr),
                    func_code=func_code,
                    name=pd.name or pd.code or str(addr),
                    code=pd.code or str(addr),
                    value=0,
                    frame_type=ft,
                    fc=pd.fc or "",
                )
                self.point_manager.add_point(slave_id, point)

                # 添加到模拟控制器
                self.simulation_controller.add_point(point, SimulateMethod.Random, 1)
                self.simulation_controller.set_point_status(point, True)

                added_count += 1

        if added_count > 0:
            self.log.info(f"IEC61850 ICD 模型加载: 已注册 {added_count} 个测点到 PointManager")

    def check_iec61850_model_cache(self) -> dict:
        """检查当前设备是否有可用的远程模型缓存

        Returns:
            {"cache_exists": bool, "cache_key": str}
        """
        if self.protocol_type != ProtocolType.Iec61850Client:
            return {"cache_exists": False, "cache_key": ""}
        if not self.protocol_handler:
            return {"cache_exists": False, "cache_key": ""}
        if isinstance(self.protocol_handler, IEC61850ClientHandler):
            return self.protocol_handler.check_model_cache()
        return {"cache_exists": False, "cache_key": ""}

    def iec61850_load_model_from_cache(self) -> bool:
        """从缓存加载 IEC61850 模型（不进行 MMS 在线发现）

        Returns:
            缓存命中且加载成功返回 True
        """
        if self.protocol_type != ProtocolType.Iec61850Client:
            return False
        if not self.protocol_handler:
            return False
        self._clear_iec61850_cache()
        if isinstance(self.protocol_handler, IEC61850ClientHandler):
            return self.protocol_handler.load_model_from_cache()
        return False

    def iec61850_remote_discover_model(self) -> bool:
        """远程发现 IEC61850 模型（需要 MMS 连接）

        发现前先清除内存中所有相关缓存（测点、模拟控制器等），
        然后开始远程发现，通过 _on_iec61850_points_discovered 回调逐批注册新测点。

        Returns:
            是否发现成功
        """
        if self.protocol_type != ProtocolType.Iec61850Client:
            return False
        if not self.protocol_handler:
            return False
        # 清除内存缓存
        self._clear_iec61850_cache()
        if isinstance(self.protocol_handler, IEC61850ClientHandler):
            return self.protocol_handler.remote_discover_model()
        return False

    def _on_iec61850_points_discovered(self, discovered_points: list) -> None:
        """处理 IEC61850 客户端发现的测点，自动注册到系统

        Args:
            discovered_points: 发现的测点列表，
                每个元素为 {"address": str, "frame_type": int, "ref": str, "code": str}
                address 为完整 IEC 61850 引用路径，如 "MEAS/M0GGIO1.AnIn1.mag.f"
                code 为短编码，简单地址模式为原始地址(如 "1")，ICD 模式为 "LN.DO"(如 "M0GGIO1.AnIn1")
        """
        frame_type_names = {0: "遥测", 1: "遥信", 2: "遥控", 3: "遥调"}
        added_count = 0
        slave_id = 1  # IEC61850 默认使用从机地址 1

        # GOOSE 控制块只作为发现结果缓存；订阅必须在设备 GOOSE 页面
        # 选择本机网卡并显式确认，不能在发现回调中产生隐式配置写入。

        for dp in discovered_points:
            if dp.get("_type") == "goose":
                continue
            addr = dp["address"]
            ft = dp["frame_type"]
            dp["ref"]

            # 检查是否已存在（根据 address + frame_type 去重）
            existing = self.point_manager.find_point_by_address_and_type(addr, ft)
            if existing:
                continue

            # 根据 frame_type 创建对应的 BasePoint 对象
            # 优先使用 code 字段（短编码），否则回退到 address
            auto_code = dp.get("code", str(addr))
            frame_type_names.get(ft, str(ft))
            auto_name = dp.get("name", dp.get("code", str(addr)))
            point_fc = dp.get("fc", "")

            point = None
            if ft == 0:  # 遥测
                point = Yc(
                    rtu_addr=str(slave_id),
                    address=str(addr),
                    func_code=3,
                    name=auto_name,
                    code=auto_code,
                    value=0,
                    frame_type=0,
                    fc=point_fc,
                )
            elif ft == 1:  # 遥信
                point = Yx(
                    rtu_addr=str(slave_id),
                    address=str(addr),
                    func_code=1,
                    name=auto_name,
                    code=auto_code,
                    value=0,
                    frame_type=1,
                    fc=point_fc,
                )
            elif ft == 2:  # 遥控
                point = Yk(
                    rtu_addr=str(slave_id),
                    address=str(addr),
                    func_code=5,
                    name=auto_name,
                    code=auto_code,
                    value=0,
                    frame_type=2,
                    fc=point_fc,
                )
            elif ft == 3:  # 遥调
                point = Yt(
                    rtu_addr=str(slave_id),
                    address=str(addr),
                    func_code=6,
                    name=auto_name,
                    code=auto_code,
                    value=0,
                    frame_type=3,
                    fc=point_fc,
                )

            if point:
                # 添加到测点管理器
                self.point_manager.add_point(slave_id, point)

                # 添加到模拟控制器
                self.simulation_controller.add_point(point, SimulateMethod.Random, 1)
                self.simulation_controller.set_point_status(point, True)

                added_count += 1
        if added_count > 0:
            self.log.info(f"IEC61850 自动发现并添加了 {added_count} 个测点")
        else:
            self.log.info("IEC61850 未发现需要新增的测点（所有测点已存在）")

    # ===== 设备启停 =====

    async def start(self) -> bool:
        """启动设备"""
        try:
            self.point_calculator.start()
            if self.protocol_handler:
                return await self.protocol_handler.start()
            return False
        except Exception as e:
            self.log.error(f"启动设备失败: {e}")
            return False

    async def stop(self) -> bool:
        """停止设备"""
        try:
            await asyncio.to_thread(self.data_update_thread.stop, 6.0)
            await asyncio.to_thread(self.simulation_controller.stop_simulation, 1.0)
            self.point_calculator.stop()
            if self.protocol_handler:
                return await self.protocol_handler.stop()
            return True
        except Exception as e:
            self.log.error(f"停止设备失败: {e}")
            return False

    # ===== 数据读取（委托给 DataReader） =====

    def update_data(self) -> None:
        """更新设备数据（使用异步批量读取优化）

        自动读取的后台线程调用此方法，改为使用异步批量读取路径：
        对于 Modbus 客户端会将连续地址合并为一次请求；
        对于 IEC61850 客户端会按类型分组批量读取；
        对于服务端和其他协议回退到逐点读取。

        重要：对于使用 AsyncModbusClient 的客户端，必须通过
        run_coroutine_threadsafe() 将协程调度到客户端连接时的事件循环上，
        而不是用 asyncio.run() 创建新的事件循环，否则会导致连接断裂。
        """
        try:
            loop = self._get_event_loop_for_update()
            if loop and loop.is_running():
                # 将协程调度到正确的事件循环（客户端连接时所在的循环）
                future = asyncio.run_coroutine_threadsafe(self._update_data_async(), loop)
                future.result(timeout=5)  # 最多等待5秒
            else:
                # 回退：无可用事件循环时使用 asyncio.run()（兼容非客户端场景）
                asyncio.run(self._update_data_async())
        except Exception as e:
            if self._logger_initialized:
                self.log.error(f"update_data error: {e}")
            else:
                print(f"update_data error: {e}")
        time.sleep(0.5)

    def _get_event_loop_for_update(self):
        """获取数据更新应使用的事件循环

        对于客户端协议（使用异步客户端如 AsyncModbusClient），
        必须使用客户端连接时所在的事件循环，否则 async 操作会失败。
        """
        if self.protocol_handler and isinstance(self.protocol_handler, ClientHandler):
            loop = getattr(self.protocol_handler, "_loop", None)
            if loop:
                return loop
        return None

    async def _update_data_async(self) -> None:
        """异步批量更新设备数据"""
        for slave_id in self.slave_id_list:
            yc_list = self.yc_dict.get(slave_id, [])
            yx_list = self.yx_dict.get(slave_id, [])
            await self.getSlaveRegisterValuesAsync(yc_list, yx_list)

    def getSlaveRegisterValues(self, yc_list: list[Yc], yx_list: list[Yx]) -> None:
        """从协议处理器获取数据值"""
        self.data_reader.get_slave_values(yc_list, yx_list)

    async def getSlaveRegisterValuesAsync(
        self, yc_list: list[Yc], yx_list: list[Yx], interval_ms: int | None = 0
    ) -> tuple[int, int]:
        """从协议处理器获取数据值（异步版，支持批量读取优化）"""
        return await self.data_reader.get_slave_values_async(yc_list, yx_list, interval_ms)

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

    async def single_read(self, event_emitter=None, interval_ms: int | None = 0) -> dict[str, int]:
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

            s_count, f_count = await self.getSlaveRegisterValuesAsync(yc_list, yx_list, interval_ms=interval_ms)
            success_total += s_count
            fail_total += f_count

        return {"success": success_total, "fail": fail_total}

    # ===== 测点操作（委托给 PointOperator） =====

    def read_single_point(self, point_code: str, slave_id: int | None = None) -> float | str | None:
        """读取单个测点的值"""
        return self.point_operator.read_single_point(point_code, slave_id)

    async def read_single_point_async(self, point_code: str, slave_id: int | None = None) -> float | str | None:
        """异步读取单个测点的值（读取本地缓存，不发送网络请求）"""
        return await self.point_operator.read_single_point_async(point_code, slave_id)

    async def active_read_single_point_async(self, point_code: str, slave_id: int | None = None) -> float | str | None:
        """主动读取单个测点的值（发送网络请求获取最新值）"""
        return await self.point_operator.active_read_single_point_async(point_code, slave_id)

    async def send_iec104_interrogation(self) -> bool:
        """发送 IEC104 总召唤命令(C_IC_NA_1)

        触发后服务端会发送所有点的最新值，c104 库自动更新本地缓存，
        然后同步到应用层测点。

        Returns:
            bool: 是否成功发送
        """
        from src.device.protocol.iec104_handler import IEC104ClientHandler

        if not isinstance(self.protocol_handler, IEC104ClientHandler):
            self.log.error("仅 IEC104 客户端支持总召唤")
            return False

        if not self.protocol_handler.is_running:
            self.log.error("IEC104 客户端未连接")
            return False

        # 发送总召唤
        result = await self.protocol_handler.send_interrogation()
        if result:
            # 等待总召唤响应到达
            import asyncio

            await asyncio.sleep(0.5)
            # 同步所有从机的缓存值到应用层测点
            for slave_id in self.slave_id_list:
                self._sync_iec104_client_values(slave_id)
            self.log.info("总召唤完成，已同步所有从机数据")
        return result

    async def send_dlt645_command(self, command: str, params: dict | None = None) -> dict:
        """发送 DL/T645 特殊命令（主站/从站功能）

        主站（Dlt645Client）支持：读/写通讯地址、广播校时、冻结命令、
        更改通信速率、修改密码、最大需量清零、电表清零、事件清零。
        从站（Dlt645Server）支持：写通讯地址、校时、设置密码、数据清零。

        Args:
            command: 命令名
            params: 命令参数（地址/速率/密码等）

        Returns:
            {"ok": bool, "message": str, "detail": dict | None}
        """
        from src.device.protocol.dlt645_handler import (
            DLT645ClientHandler,
            DLT645ServerHandler,
        )

        handler = self.protocol_handler
        if not isinstance(handler, (DLT645ClientHandler, DLT645ServerHandler)):
            self.log.error("仅 DLT645 设备支持特殊命令")
            return {"ok": False, "message": "仅 DLT645 设备支持特殊命令"}

        # dlt645 3.0.0 的 send_command 为原生异步实现，直接等待
        result = await handler.send_command(command, params or {})

        # 更改通信速率成功后，同步本地配置，使设备信息接口返回新速率
        if result.get("ok") and command == "change_baud_rate":
            baud = (params or {}).get("baud")
            if baud is not None:
                try:
                    self.baudrate = int(baud)
                except (TypeError, ValueError):
                    pass

        # 写通讯地址成功后，同步本地电表地址（主站记录对端地址，从站记录自身地址）
        if result.get("ok") and command == "write_address":
            address = (params or {}).get("address")
            if address:
                self.meter_address = str(address)

        # 写入值成功后，从服务端实例映射重新读取对应点并更新点表缓存，
        # 使表格"真实值"列立即反映新值（与写全局 DIMap 不同，实例映射是读值来源）
        if result.get("ok") and command == "write_value":
            self._sync_dlt645_points_after_write(handler, params)

        return result

    def _sync_dlt645_points_after_write(self, handler, params: dict | None = None) -> None:
        """write_value 写入成功后，将服务端 data_map 中的新值同步到点表缓存。

        DLT645 从站表格真实值读取自 point.real_value（点模型缓存），
        而写入只修改了服务端实例映射，需重新读取对应点以刷新缓存。
        直接从实例映射取原始工程值，避免 read_value 的寄存器整数换算截断精度。
        """
        from src.device.protocol.dlt645_handler import DLT645ServerHandler

        if not isinstance(handler, DLT645ServerHandler):
            return
        di_str = str((params or {}).get("di", "")).strip()
        try:
            di = int(di_str, 16)
        except ValueError:
            return
        server = getattr(handler, "server", None)
        if server is None:
            return

        def _raw_primary(item) -> float | None:
            from dlt645.model.types.dlt645_type import Demand

            def extract(value):
                if isinstance(value, Demand):
                    value = value.value
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    return float(value)
                return None

            if isinstance(item, list):
                for it in item:
                    if it is None:
                        continue
                    val = extract(getattr(it, "value", None))
                    if val is not None:
                        return val
                return None
            return extract(getattr(item, "value", None))

        item = server.get_data_item(di)
        if item is None:
            return
        raw = _raw_primary(item)
        if raw is None:
            return
        for point in self.point_manager.get_all_points():
            try:
                if int(point.address) == di:
                    point.real_value = raw
                    point.is_valid = True
            except (TypeError, ValueError):
                continue

    async def read_point_metadata_async(self, point_code: str, slave_id: int | None = None) -> dict:
        """异步读取测点的品质(q)与时标(t)元数据"""
        return await self.point_operator.read_metadata_async(point_code, slave_id)

    def editPointData(
        self,
        point_code: str,
        real_value: float,
        source: ChangeSource | None = None,
        detail: str | None = None,
        slave_id: int | None = None,
    ) -> bool:
        """编辑测点值"""
        return self.point_operator.edit_value(point_code, real_value, source, detail, slave_id)

    async def edit_point_data_async(
        self,
        point_code: str,
        real_value: float,
        source: ChangeSource | None = None,
        detail: str | None = None,
        slave_id: int | None = None,
    ) -> bool:
        """异步编辑测点值"""
        return await self.point_operator.edit_value_async(point_code, real_value, source, detail, slave_id)

    def edit_point_metadata(self, point_code: str, metadata: dict) -> bool:
        """编辑测点元数据"""
        return self.point_operator.edit_metadata(point_code, metadata)

    def edit_point_limit(self, point_code: str, min_value_limit: int, max_value_limit: int) -> bool:
        """编辑测点限值"""
        return self.point_operator.edit_limit(point_code, min_value_limit, max_value_limit)

    def get_point_data(self, point_code_list: list[str]) -> BasePoint | None:
        """获取测点"""
        return self.point_operator.get_point_data(point_code_list)

    def resetPointValues(self) -> None:
        """重置所有测点值"""
        self.point_manager.reset_all_values()

    # ===== 动态测点/从机管理（委托给组件） =====

    def add_point_dynamic(self, channel_id: int, frame_type: int, point_data: dict) -> bool:
        """动态添加测点"""
        return self.point_operator.add_point_dynamic(channel_id, frame_type, point_data)

    def add_points_dynamic_batch(self, channel_id: int, frame_type: int, points_data_list: list[dict]) -> bool:
        """动态批量添加测点"""
        return self.point_operator.add_points_dynamic_batch(channel_id, frame_type, points_data_list)

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

    def setAllPointSimulateMethod(self, simulate_method: str | SimulateMethod) -> None:
        """设置所有点的模拟方法"""
        try:
            method = SimulateMethod(simulate_method)
            self.simulation_controller.set_all_point_simulate_method(method)
        except ValueError:
            self.log.error(f"无效的模拟方法: {simulate_method}")

    def setSinglePointSimulateMethod(self, point_code: str, simulate_method: str | SimulateMethod) -> bool:
        """设置单个点的模拟方法"""
        try:
            method = SimulateMethod(simulate_method)
            return self.simulation_controller.set_single_point_simulate_method(point_code, method)
        except ValueError:
            self.log.error(f"无效的模拟方法: {simulate_method}")
            return False

    def setSinglePointStep(self, point_code: str, step: float) -> bool:
        return self.simulation_controller.set_single_point_step(point_code, step)

    def setSinglePointFixedValue(self, point_code: str, fixed_value: float | int) -> bool:
        return self.simulation_controller.set_single_point_fixed_value(point_code, fixed_value)

    def setSinglePointStatus(self, point_code: str, is_running: bool) -> bool:
        """按测点编码设置模拟启停状态"""
        return self.simulation_controller.set_point_status_by_code(point_code, is_running)

    def getSimulationConfig(self) -> list[dict]:
        """获取整机测点模拟配置（回显用）"""
        configs: list[dict] = []
        for point, simulator in self.simulation_controller.points.items():
            configs.append(
                {
                    "point_code": point.code,
                    "name": point.name,
                    "frame_type": getattr(point, "frame_type", None),
                    "simulate_method": simulator.simulate_method.value,
                    "step": simulator.step,
                    "fixed_value": simulator.fixed_value,
                    "enabled": simulator.is_running,
                }
            )
        return configs

    def applySimulationConfig(self, items: list[dict]) -> dict:
        """批量应用测点模拟配置（是否模拟 + 模拟方式 + 步长）。

        配置是"要模拟的测点"的完整定义：未包含在配置中的测点将被禁用模拟，
        避免仅启用已选点、其余保持默认全量模拟。批量场景不打逐点日志。
        """
        applied, failed = self.simulation_controller.apply_configuration(items)
        self.log.info(f"应用模拟配置: 成功 {len(applied)} 个测点, 失败 {len(failed)} 个")
        return {"applied": applied, "failed": failed}

    def getPointInfo(self, point_code: str) -> dict:
        return self.simulation_controller.get_point_info(point_code)

    def getPointsValues(self, point_codes: list[str]) -> dict[str, float | int | str | None]:
        """批量获取测点当前值（轻量，供自动刷新；仅返回存在的测点）"""
        values: dict[str, float | int | str | None] = {}
        for code in point_codes:
            point = self.point_manager.get_point_by_code(code)
            if point is None:
                continue
            values[code] = point.real_value if isinstance(point, (Yc, Yt)) else point.value
        return values

    def setPointSimulationRange(self, point_code: str, min_value: float, max_value: float) -> bool:
        return self.simulation_controller.set_point_simulation_range(point_code, min_value, max_value)

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

    def importDataPointFromChannel(self, channel_id: int, protocol_type: ProtocolType = ProtocolType.ModbusTcp) -> None:
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

    def get_table_head(self) -> list[str]:
        return self.data_exporter.get_table_head()

    def get_table_data(
        self,
        slave_id: int,
        name: str | None = None,
        page_index: int | None = 1,
        page_size: int | None = 10,
        point_types: list[int] | None = None,
        order_by: str | None = None,
        order_direction: str | None = None,
        iec104_types: list[str] | None = None,
        dlt645_prefix: int | None = None,
        dlt645_settlement: int | None = None,
    ) -> tuple[list[list[str]], int]:
        # 对于 IEC104 客户端，在获取表格数据前同步 c104.Point 的值到内部点
        if self.protocol_type == ProtocolType.Iec104Client and self.protocol_handler:
            if self.protocol_handler.is_running:
                self._sync_iec104_client_values(slave_id)

        # Determine if we should mask errors (only for Client devices)
        mask_error = self.protocol_type in [
            ProtocolType.ModbusTcpClient,
            ProtocolType.ModbusRtuClient,
            ProtocolType.Iec104Client,
            ProtocolType.Dlt645Client,
            ProtocolType.Iec61850Client,
        ]

        return self.data_exporter.get_table_data(
            slave_id,
            name,
            page_index,
            page_size,
            point_types,
            mask_error=mask_error,
            order_by=order_by,
            order_direction=order_direction,
            iec104_types=iec104_types,
            dlt645_prefix=dlt645_prefix,
            dlt645_settlement=dlt645_settlement,
        )

    def _sync_iec104_client_values(self, slave_id: int) -> None:
        """同步 IEC104 客户端从服务端接收的值到内部测点"""
        self.data_reader.sync_iec104_client_values(slave_id)

    # ===== 报文捕获（委托给 MessageFormatter） =====

    def get_messages(self, limit: int | None = None) -> list[dict]:
        """获取报文历史记录"""
        return self.message_formatter.get_messages(limit)

    def get_message_detail(self, sequence_id: int) -> dict | None:
        return self.message_formatter.get_message_detail(sequence_id)

    def clear_messages(self) -> None:
        """清空报文历史记录"""
        self.message_formatter.clear_messages()

    def get_avg_time(self) -> dict:
        """获取平均收发时间"""
        return self.message_formatter.get_avg_time()

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
    def frame_type_dict() -> dict[int, str]:
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

    def setRelatedPoint(self, point: BasePoint, related_point: BasePoint) -> None:
        """设置测点关联"""
        self.point_operator.set_related_point(point, related_point)

    def reload_mappings(self, mappings: list[dict[str, Any]] | None = None) -> None:
        """重新加载测点映射"""
        if self.point_calculator:
            self.point_calculator.reload_mappings(mappings)

    def set_device_provider(self, provider: Any, mappings: list[dict[str, Any]] | None = None) -> None:
        """设置设备提供者"""
        if self.point_calculator:
            self.point_calculator.set_device_provider(provider, mappings)
