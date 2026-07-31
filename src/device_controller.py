import asyncio
from contextlib import suppress
import json
import os.path
import threading
import time

from src.config.config import Config
from src.config.global_config import CONFIG_JSON_DIR
from src.config.storage import get_storage_path
from src.data.service.channel_configuration_service import ChannelConfigurationService
from src.data.service.channel_service import ChannelService
from src.device.core.device import Device
from src.device.data_update.data_update_thread import DataUpdateThread
from src.device.factory.general_device_builder import GeneralDeviceBuilder
from src.device.types.circuit_breaker import CircuitBreaker
from src.device.types.general_device import GeneralDevice
from src.device.types.pcs import Pcs
from src.enums.data_source import DataSource
from src.enums.modbus_def import ProtocolType, get_protocol_type_by_value
from src.log import log


class DeviceController:
    config_json_path = os.path.join(CONFIG_JSON_DIR, "config.json")

    def __init__(self):
        # 指定列表类型为ModbusServer
        self.device_list: list[Device] = []
        # 当前选中的ModbusServer
        self.current_device: Device = Device()
        # 根据名称映射ModbusServer
        self.device_map = {}
        # 设备导入将在get_device_controller中异步进行
        self.enerey_meter: Device | None = None
        # 数据同步线程
        self.data_sync_thread: DataUpdateThread = DataUpdateThread(task=self._sync_task)

    def _sync_task(self):
        """数据同步任务，每秒执行一次"""
        self.sync_pcs_power_to_meter()
        time.sleep(1)  # 每秒执行一次

    def start_data_sync_thread(self):
        """启动数据同步线程"""
        try:
            self.data_sync_thread.start()
            log.info("PCS功率同步线程已启动")
        except Exception as e:
            log.error(f"启动PCS功率同步线程失败: {e}")

    def get_device_name_list(self):
        device_name_list = []
        for device in self.device_list:
            device_name_list.append(device.name)
        return device_name_list

    def get_slave_list(self):
        slave_list = []
        for i in range(0, self.current_device.server.slave_cnt):
            slave_list.append("从机" + str(i + 1))
        slave_list.append("返回上级菜单")
        return slave_list

    def get_device_by_id(self, device_id: int) -> Device | None:
        """根据设备 ID 查找设备"""
        for device in self.device_list:
            if getattr(device, "device_id", None) == device_id:
                return device
        return None

    def get_device_by_channel_id(self, channel_id: int) -> Device | None:
        """根据通道 ID 查找设备（创建设备时 device_id == channel_id）"""
        for device in self.device_list:
            if getattr(device, "device_id", None) == channel_id:
                return device
        return None

    async def remove_device_by_id(self, device_id: int) -> bool:
        """根据设备 ID 停止并移除设备"""
        device = self.get_device_by_id(device_id)
        if not device:
            return False

        # 停止设备
        try:
            await device.stop()
        except Exception as e:
            log.error(f"移除设备 {device.name} (ID: {device_id}) 时出错: {e}")

        # 从列表和映射中移除
        if device in self.device_list:
            self.device_list.remove(device)

        # 移除映射中的条目（可能存在多个指向同一对象的映射，例如旧名称和新名称）
        keys_to_remove = [k for k, v in self.device_map.items() if v == device]
        for k in keys_to_remove:
            del self.device_map[k]

        # 如果是储能电表，清理变量
        if self.enerey_meter == device:
            self.enerey_meter = None

        from src.config.log.device_logger import DeviceLoggerManager

        DeviceLoggerManager.unregister_device(device.name)
        return True

    def sync_pcs_power_to_meter(self):
        """同步所有PCS功率之和到储能电表"""
        try:
            total_power = 0.0

            # 计算所有PCS设备的功率之和
            for device in self.device_list:
                if device.name.upper().find("PCS") != -1:
                    # 获取PCS的功率值（假设测点编码为"totalAcP"）
                    power_point = device.get_point_data(["totalAcP"])
                    if power_point:
                        total_power += power_point.real_value

            # 将功率之和设置到储能电表的指定测点（假设测点编码为"pcs_total_power"）
            if self.enerey_meter:
                self.enerey_meter.editPointData("power", total_power)
                log.info(f"同步PCS总功率到储能电表: {total_power}")
        except Exception as e:
            log.error(f"同步PCS功率到电表失败: {e}")

    async def import_device_from_db(self):
        """在线程中导入数据库设备，避免阻塞 FastAPI 事件循环。"""
        await asyncio.to_thread(self._import_device_from_db)

    def _import_device_from_db(self):
        try:
            channel_list = ChannelService.get_all_channels()

            # 设备构建包含同步数据库访问，统一放在工作线程内顺序执行。
            def _build_device(channel):
                """单个设备的构建逻辑"""
                channel_code = channel["code"]
                channel_name = channel["name"]
                channel_id = channel["id"]
                channel["protocol_type"]
                conn_type = channel["conn_type"]
                ip = channel.get("ip", Config.DEFAULT_IP)
                port = channel.get("port", Config.DEFAULT_PORT)

                log.info(f"导入设备: {channel_code}")

                # 获取协议类型枚举
                channel_protocol_type = ChannelService.get_protocol_type(channel)

                if channel_code.upper().find("PCS") != -1:
                    general_device_builder = GeneralDeviceBuilder(channel_id=channel_id, device=Pcs())
                elif channel_code.upper().find("BREAKER") != -1:
                    log.info(f"导入断路器设备: {channel_code}")
                    general_device_builder = GeneralDeviceBuilder(channel_id=channel_id, device=CircuitBreaker())
                else:
                    general_device_builder = GeneralDeviceBuilder(channel_id=channel_id, device=GeneralDevice())

                # 设置网络/串口配置
                if conn_type in [0, 3]:  # 串口连接（主站或从站）
                    general_device_builder.setDeviceSerialConfig(
                        serial_port=channel.get("com_port", ""),
                        baudrate=channel.get("baud_rate", 9600),
                        databits=channel.get("data_bits", 8),
                        stopbits=channel.get("stop_bits", 1),
                        parity=channel.get("parity", "E"),
                    )
                elif (
                    channel_protocol_type == ProtocolType.Iec104Client
                    or channel_protocol_type == ProtocolType.ModbusTcpClient
                    or channel_protocol_type == ProtocolType.Dlt645Client
                    or channel_protocol_type == ProtocolType.Iec61850Client
                ):  # TCP 客户端
                    general_device_builder.setDeviceNetConfig(port=port, ip=ip)
                else:  # TCP 服务端
                    general_device_builder.setDeviceNetConfig(port=port, ip=Config.DEFAULT_IP)

                # 传递 IEC61850 IED 模型名称
                if channel_protocol_type in (ProtocolType.Iec61850Server, ProtocolType.Iec61850Client):
                    model_name = channel.get("model_name")
                    if model_name:
                        general_device_builder.setDeviceModelName(model_name)
                    # v2.0: 传递 ICD 文件路径
                    icd_path = channel.get("icd_path")
                    if icd_path:
                        general_device_builder.setDeviceIcdPath(icd_path)

                # 协议参数和 TLS 配置均以数据库记录为准。旧通道没有记录时，
                # get_protocol_params 会写入当前协议/连接模式的默认配置。
                general_device_builder.setDeviceRuntimeConfig(
                    ChannelConfigurationService.get_protocol_params(
                        channel_id,
                        channel.get("protocol_type", 1),
                        conn_type,
                    )["values"]
                )
                general_device_builder.setDeviceSecurityConfig(
                    ChannelConfigurationService.get_runtime_security(channel_id)
                )

                general_device = general_device_builder.makeGeneralDevice(
                    device_id=channel_id,
                    device_name=channel_name,
                    protocol_type=channel_protocol_type,
                    is_start=False,
                )
                general_device.name = channel_name

                # 特殊处理储能电表
                is_energy_meter = (
                    channel_protocol_type == ProtocolType.Dlt645Client
                    or channel_protocol_type == ProtocolType.Dlt645Server
                )

                return general_device, is_energy_meter

            results = []
            for channel in channel_list:
                try:
                    results.append(_build_device(channel))
                except Exception as exc:
                    results.append(exc)

            # 收集结果
            for result in results:
                if isinstance(result, Exception):
                    log.error(f"创建设备失败: {result}")
                    continue
                general_device, is_energy_meter = result
                if general_device is not None:
                    self.device_list.append(general_device)
                    self.device_map[general_device.name] = general_device
                    if is_energy_meter:
                        self.enerey_meter = general_device

            # 所有设备创建完成后，设置提供者（此时可以安全地解析跨设备依赖）
            from src.data.service.point_mapping_service import PointMappingService

            mappings = PointMappingService.get_all_mappings()
            for device in self.device_list:
                device.set_device_provider(self, mappings)

        except Exception as e:
            log.error(f"通过数据库导入失败: {e}")
            raise

    async def import_device_from_json(self, file_path=config_json_path):
        """在线程中读取并构建设备，避免同步文件 I/O 阻塞事件循环。"""
        await asyncio.to_thread(self._import_device_from_json, file_path)

    def _import_device_from_json(self, file_path=config_json_path):
        if file_path:
            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)
                    for device in data:
                        device_id = device["id"]
                        device["type"]
                        protocol_type = get_protocol_type_by_value(device["protocol_type"])
                        default_status = device["default_status"]
                        path = device["csv_path"]
                        is_start = default_status == "start"
                        builder = GeneralDeviceBuilder()
                        other_device_path = os.path.join(
                            get_storage_path("point_table_cache_directory"),
                            path.lstrip("/\\"),
                        )
                        other_device = builder.makeOtherDevice(device_id, other_device_path, protocol_type, is_start)
                        self.device_list.append(other_device)
                        self.device_map[other_device.name] = other_device
                log.info("通过csv文件导入设备配置文件成功!")

                # 启动数据同步线程
                # self.start_data_sync_thread()

                # 所有设备创建完成后，设置提供者
                from src.data.service.point_mapping_service import PointMappingService

                mappings = PointMappingService.get_all_mappings()
                for device in self.device_list:
                    device.set_device_provider(self, mappings)

            except Exception as e:
                log.error(f"通过csv文件导入设备配置文件失败: {e}")

    # 读取配置文件创建设备
    async def import_device(self):
        if Config.data_source == DataSource.Db:
            await self.import_device_from_db()
        else:
            config_json_path = os.path.join(CONFIG_JSON_DIR, "config.json")
            await self.import_device_from_json(config_json_path)

    async def create_modbus_server(self):
        await self.import_device()

        if self.device_list:
            self.current_device = self.device_list[0]

    # 结束所有ModbusTcpServer
    async def stop_all_modbus_server(self):
        for device in tuple(self.device_list):
            await device.stop()

        # 停止数据同步线程
        if self.data_sync_thread:
            await asyncio.to_thread(self.data_sync_thread.stop, 2.0)
            log.info("数据同步线程已停止")

    async def shutdown(self) -> None:
        """释放控制器拥有的设备、线程、协议和日志资源。"""
        await self.stop_all_modbus_server()

        from src.config.log.device_logger import DeviceLoggerManager

        for device in tuple(self.device_list):
            DeviceLoggerManager.unregister_device(device.name)
        self.device_list.clear()
        self.device_map.clear()
        self.enerey_meter = None

        # 默认 current_device 不一定属于 device_list，也需要释放计算线程池。
        if self.current_device is not None:
            self.current_device.point_calculator.stop()


device_controller: DeviceController | None = None
_device_controller_init_task: asyncio.Task[DeviceController] | None = None
_device_controller_guard = threading.Lock()


async def _create_device_controller() -> DeviceController:
    controller = DeviceController()
    try:
        await controller.import_device()
    except BaseException:
        with suppress(Exception):
            await controller.shutdown()
        raise
    return controller


async def get_device_controller() -> DeviceController:
    """获取已初始化控制器；并发调用只执行一次初始化。"""
    global device_controller, _device_controller_init_task

    if device_controller is not None:
        return device_controller

    loop = asyncio.get_running_loop()
    with _device_controller_guard:
        if device_controller is not None:
            return device_controller

        task = _device_controller_init_task
        if task is not None and task.get_loop() is not loop:
            if not task.done():
                raise RuntimeError("设备控制器正在另一个事件循环中初始化")
            try:
                device_controller = task.result()
            except BaseException:
                _device_controller_init_task = None
                task = None

        if device_controller is not None:
            return device_controller
        if task is None:
            task = loop.create_task(_create_device_controller(), name="device-controller-initialization")
            _device_controller_init_task = task

    try:
        controller = await asyncio.shield(task)
    except BaseException:
        with _device_controller_guard:
            if _device_controller_init_task is task:
                _device_controller_init_task = None
        raise

    with _device_controller_guard:
        if device_controller is None:
            device_controller = controller
        if _device_controller_init_task is task:
            _device_controller_init_task = None
        return device_controller


async def shutdown_device_controller() -> None:
    """关闭并重置全局控制器，供应用 lifespan 和测试安全复用。"""
    global device_controller, _device_controller_init_task

    with _device_controller_guard:
        controller = device_controller
        task = _device_controller_init_task
        device_controller = None
        _device_controller_init_task = None

    if controller is None and task is not None:
        try:
            controller = await asyncio.shield(task)
        except BaseException:
            controller = None

    if controller is not None:
        await controller.shutdown()
