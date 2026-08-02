"""
DLT645 协议处理器
支持 DLT645 电力表计协议服务端和客户端
"""

from collections import OrderedDict
import contextlib
from datetime import datetime
import threading
from typing import Any

from src.config.config import Config
from src.device.protocol.base_handler import ClientHandler, ServerHandler
from src.device.protocol.dlt645_compat import (
    AsyncMeterClientService,
    AsyncMeterServerService,
)
from src.enums.point_data import Yc
from src.enums.points.base_point import BasePoint


def _parse_command_datetime(value: Any) -> datetime:
    """解析命令参数中的时间，缺省返回当前时间。

    支持 ISO 格式字符串（如 "2026-08-01T12:30:00"）或 datetime 对象。
    """
    if isinstance(value, datetime):
        return value
    if value:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            return dt
        except ValueError:
            pass
    return datetime.now()


def _data_item_detail(item: Any) -> dict | None:
    """将 dlt645 库返回的 DataItem 转成前端可读的 dict。"""
    if item is None:
        return None
    return {
        "di": getattr(item, "di", None),
        "name": getattr(item, "name", None),
        "value": getattr(item, "value", None),
        "unit": getattr(item, "unit", None),
        "update_time": (getattr(item, "update_time", None).isoformat() if getattr(item, "update_time", None) else None),
    }


def _scale_point_value(value: Any, point: BasePoint | None) -> Any:
    """Yc 遥测点按系数反向换算为原始值；非数值或非遥测点原样返回。"""
    if isinstance(point, Yc) and isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return int((float(value) - point.add_coe) / point.mul_coe)
        except (ZeroDivisionError, TypeError, ValueError):
            return value
    return value


def _format_point_value(value: Any, point: BasePoint | None = None) -> Any:
    """将 dlt645 的多数据项值转成前端显示值。

    DLT645 部分数据标识（DI）含有多个数据项，例如最大需量及其发生时间
    （Demand 对象）、事件记录（EventRecord 元组 / 多个事件）。这里将
    所有数据转成可读形式，多个数据用逗号分隔。
    """
    from dlt645.model.types.dlt645_type import Demand, EventRecord

    if isinstance(value, Demand):
        # dlt645 已将协议原始数据解码为真实值。系数反向换算只用于写回
        # point.value，不能用于显示，否则自定义系数会让需量值被二次换算。
        return f"{value.value}, {value.time:%Y-%m-%d %H:%M:%S}"
    if isinstance(value, EventRecord):
        event = value.event
        if isinstance(event, (tuple, list)):
            return ", ".join(str(e) for e in event)
        return event
    if isinstance(value, (list, tuple)):
        parts = [str(_format_point_value(v, point)) for v in value]
        return ", ".join(p for p in parts if p not in ("", "None"))
    return value


def _data_item_display(item: Any, point: BasePoint | None = None) -> Any:
    """将 dlt645 返回的 DataItem（或 DataItem 列表）转成显示值。

    客户端 read_XX / 服务端 get_data_item 对复合 DI（事件记录、时标参变量等）
    会返回 DataItem 列表，此处逐项转换并用逗号分隔。
    """
    if item is None:
        return None
    if isinstance(item, list):
        parts = [str(_data_item_display(i, point)) for i in item]
        return ", ".join(p for p in parts if p not in ("", "None"))
    return _format_point_value(getattr(item, "value", item), point)


def _is_compound(item: Any) -> bool:
    """判断是否为复合 DI（含多个数据项）。

    复合数据包括：DataItem 列表（事件记录、时标参变量）、Demand（最大需量
    及其发生时间）、EventRecord 元组、以及 value 本身为 list/tuple 的情况。
    """
    from dlt645.model.types.dlt645_type import Demand, EventRecord

    if isinstance(item, list):
        return True
    value = getattr(item, "value", None)
    return isinstance(value, (Demand, EventRecord, list, tuple))


def _primary_numeric(item: Any, point: BasePoint | None = None) -> Any:
    """从 dlt645 返回的 DataItem（或列表）中提取主数值。

    测点模型（point.value / real_value）只接受数值：复合 DI 取第一个
    数值数据项（Demand 取 value 部分），并应用 Yc 系数反向换算。
    """
    if item is None:
        return 0

    def extract(value: Any):
        from dlt645.model.types.dlt645_type import Demand

        if isinstance(value, Demand):
            value = value.value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return _scale_point_value(value, point)
        return None

    if isinstance(item, list):
        for it in item:
            if it is None:
                continue
            val = extract(getattr(it, "value", None))
            if val is not None:
                return val
        return 0
    return extract(getattr(item, "value", None)) or 0


class _CaptureSequenceTracker:
    """Add stable numeric sequence IDs to dlt645's UUID-based records."""

    def __init__(self, max_records: int = 1000) -> None:
        self._max_records = max_records
        self._next_sequence = 1
        self._sequences: OrderedDict[str, int] = OrderedDict()
        self._lock = threading.Lock()

    def serialize(self, messages: list, count: int) -> list[dict]:
        result = []
        with self._lock:
            for message in messages:
                item = message.to_dict()
                record_id = str(item.get("id") or id(message))
                sequence_id = self._sequences.get(record_id)
                if sequence_id is None:
                    sequence_id = self._next_sequence
                    self._next_sequence += 1
                    self._sequences[record_id] = sequence_id
                else:
                    self._sequences.move_to_end(record_id)
                item["sequence_id"] = sequence_id
                result.append(item)

            while len(self._sequences) > self._max_records:
                self._sequences.popitem(last=False)

        return result[-count:] if count > 0 else result

    def clear(self) -> None:
        with self._lock:
            self._next_sequence = 1
            self._sequences.clear()


class DLT645ServerHandler(ServerHandler):
    """DLT645 服务端处理器

    支持 TCP 和 RTU（串口）两种连接方式。
    """

    def __init__(self, log=None):
        super().__init__()
        self._server = None
        self._log = log
        self._meter_address: str = "000000000000"
        self._capture_sequences = _CaptureSequenceTracker()
        self._is_serial: bool = False  # 是否为串口模式

    def initialize(self, config: dict[str, Any]) -> None:
        """初始化 DLT645 服务器

        Args:
            config: 配置字典，包含:
                TCP 模式:
                    - ip: 监听 IP（默认 0.0.0.0）
                    - port: 监听端口（默认 8899）
                RTU（串口）模式:
                    - serial_port: 串口号（如 COM1 或 /dev/ttyUSB0）
                    - baudrate: 波特率（默认 9600）
                    - databits: 数据位（默认 8）
                    - stopbits: 停止位（默认 1）
                    - parity: 校验位（默认 "E" 偶校验）
                通用:
                    - meter_address: 电表地址（12位BCD码）
                    - timeout: 超时时间（默认 30）
        """
        self._config = config
        timeout = config.get("timeout", 30)
        runtime = config.get("runtime", {})
        timeout = runtime.get("session_idle_timeout_ms", 30000) / 1000
        self._meter_address = config.get("meter_address", "000000000000")

        # 判断使用 TCP 还是 RTU 模式
        serial_port = config.get("serial_port")

        if serial_port:
            # RTU（串口）模式
            self._is_serial = True
            baudrate = config.get("baudrate", 9600)
            databits = config.get("databits", 8)
            stopbits = config.get("stopbits", 1)
            parity = config.get("parity", "E")

            self._server = AsyncMeterServerService.new_rtu_server(
                port=serial_port,
                data_bits=databits,
                stop_bits=stopbits,
                baud_rate=baudrate,
                parity=parity,
                timeout=timeout,
            )
        else:
            # TCP 模式
            self._is_serial = False
            ip = config.get("ip", "0.0.0.0")
            port = config.get("port", 8899)

            self._server = AsyncMeterServerService.new_tcp_server(ip=ip, port=port, timeout=timeout)

        # 确保地址是12位BCD码字符串
        addr_str = str(self._meter_address).zfill(12)
        self._server.set_address(addr_str)

        # 启用报文捕获
        self._server.enable_message_capture(queue_size=200)

    async def start(self) -> bool:
        """启动 DLT645 服务器"""
        try:
            if self._server:
                await self._server.start()
                self._is_running = True
                if self._log:
                    self._log.info(f"DLT645 服务器启动成功, 电表地址: {self._meter_address}")
                return True
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"启动 DLT645 服务器失败: {e}")
            return False

    async def stop(self) -> bool:
        """停止 DLT645 服务器"""
        try:
            if self._server:
                await self._server.stop()
                self._is_running = False
                return True
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"停止 DLT645 服务器失败: {e}")
            return False

    def read_value(self, point: BasePoint) -> Any:
        """读取测点值"""
        if self._server:
            # 每次读取先清空附加显示，避免残留上一次结果
            point._dlt645_display_extra = None
            # DLT645 使用数据标识读取，服务端直接返回内部映射值；
            # 复合 DI（最大需量+发生时间等）的完整显示值挂到测点，供表格逗号分隔展示
            item = self._server.get_data_item(point.address)
            if _is_compound(item):
                display = _data_item_display(item, point)
                if display is not None:
                    point._dlt645_display_extra = display
            # 返回数值主值更新测点模型（point.value / real_value 只接受数值）
            return _primary_numeric(item, point)
        return 0

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值"""
        if self._server:
            # 根据数据标识前缀调用相应的 set_XX 方法
            # address 是 int，转为 hex 字符串查看前缀
            hex_addr = hex(point.address)[2:].zfill(8)
            prefix = hex_addr[:2]

            try:
                method_name = f"set_{prefix}"
                if hasattr(self._server, method_name):
                    method = getattr(self._server, method_name)
                    # 服务端模式：直接写入原始映射的值
                    method(point.address, value)
                    return True
                else:
                    # 如果没有对应的前缀方法，尝试通用设置（如果库支持）
                    if self._log:
                        self._log.warning(f"DLT645 服务端暂不支持 DI 前缀 {prefix} (addr: {hex_addr})")
                    return False
            except Exception as e:
                if self._log:
                    self._log.error(f"DLT645 写入数据失败: {e}")
                return False
        return False

    def add_points(self, points: list[BasePoint]) -> None:
        """添加测点（DLT645 按数据标识访问，无需预先添加）"""
        pass

    def get_value_by_address(self, func_code: int, slave_id: int, address: int) -> Any:
        """根据地址获取值"""
        if self._server:
            return _data_item_display(self._server.get_data_item(address))
        return 0

    def set_value_by_address(self, func_code: int, slave_id: int, address: int, value: Any) -> None:
        """根据地址设置值"""
        if self._server:
            hex_addr = hex(address)[2:].zfill(8)
            prefix = hex_addr[:2]

            try:
                method_name = f"set_{prefix}"
                if hasattr(self._server, method_name):
                    method = getattr(self._server, method_name)
                    method(address, value)
                elif self._log:
                    self._log.warning(f"DLT645 set_value_by_address 暂不支持 DI 前缀 {prefix} (addr: {hex_addr})")
            except Exception as e:
                if self._log:
                    self._log.error(f"DLT645 set_value_by_address 失败: {e}")

    def set_meter_address(self, address: str) -> None:
        """设置电表地址"""
        self._meter_address = address
        if self._server:
            self._server.set_address(address)

    def clear_meter_data(self) -> None:
        """清除电表数据"""
        if self._server and hasattr(self._server, "clear_meter_data"):
            self._server.clear_meter_data()

    async def send_command(self, command: str, params: dict | None = None) -> dict:
        """执行 DL/T645 从站（模拟电表）侧特殊命令

        从站直接操作内部状态，模拟电表收到主站命令后的效果：
        - write_address: 写通讯地址（设置电表地址） params: address(12位数字)
        - set_time: 校时（设置电表时间） params: datetime(可选, ISO 字符串)
        - change_password: 设置密码（修改密码） params: password(8位数字)
        - clear_demand: 最大需量清零（清空全部需量数据）
        - clear_meter: 电表清零（清空电能量/需量/冻结/事件等累计数据）
        - clear_event: 事件清零（清空事件记录）

        Returns:
            {"ok": bool, "message": str, "detail": dict | None}
        """
        params = params or {}
        if not self._server:
            return {"ok": False, "message": "DLT645 服务端未初始化"}

        try:
            if command == "write_address":
                address = str(params.get("address", "")).strip()
                if len(address) != 12 or not address.isdigit():
                    return {"ok": False, "message": "通讯地址必须为 12 位数字"}
                self._server.set_address(address)
                self._meter_address = address
                if self._log:
                    self._log.info(f"DLT645 从站通讯地址已设置为: {address}")
                return {
                    "ok": True,
                    "message": f"通讯地址已设置为 {address}",
                    "detail": {"address": address},
                }

            if command == "set_time":
                dt = _parse_command_datetime(params.get("datetime"))
                from dlt645.common.transform import uint8_to_bcd

                data = bytearray(
                    [
                        uint8_to_bcd(dt.year % 100),
                        uint8_to_bcd(dt.month),
                        uint8_to_bcd(dt.day),
                        uint8_to_bcd(dt.hour),
                        uint8_to_bcd(dt.minute),
                        uint8_to_bcd(dt.second),
                    ]
                )
                self._server.set_time(data)
                if self._log:
                    self._log.info(f"DLT645 从站电表时间已设置为: {dt:%Y-%m-%d %H:%M:%S}")
                return {
                    "ok": True,
                    "message": f"电表时间已设置为 {dt:%Y-%m-%d %H:%M:%S}",
                    "detail": {"datetime": dt.isoformat()},
                }

            if command == "change_password":
                password = str(params.get("password", "")).strip()
                if len(password) != 8 or not password.isdigit():
                    return {"ok": False, "message": "密码必须为 8 位数字"}
                self._server.set_password(password)
                if self._log:
                    self._log.info("DLT645 从站密码已修改")
                return {"ok": True, "message": "密码修改成功"}

            if command == "clear_demand":
                from dlt645.model.data.data_handler import set_data_item
                from dlt645.model.data.define import DIMap
                from dlt645.model.types.dlt645_type import Demand

                # 需量清零：清空全部 DI 前缀为 0x01 的需量数据（含发生时间）
                count = 0
                for di, item in DIMap.items():
                    if (di >> 24) & 0xFF != 0x01 or isinstance(item, list):
                        continue
                    if set_data_item(di, Demand(0.0, datetime.now())):
                        count += 1
                if self._log:
                    self._log.info(f"DLT645 从站最大需量清零完成，共 {count} 项")
                return {
                    "ok": True,
                    "message": f"最大需量清零成功，共 {count} 项",
                    "detail": {"count": count},
                }

            if command == "clear_meter":
                self._server._reset_energy_data()
                self._server._reset_event_records(0xFFFFFFFF)
                if self._log:
                    self._log.info("DLT645 从站电表数据已清零")
                return {"ok": True, "message": "电表数据已清零"}

            if command == "clear_event":
                self._server._reset_event_records(0xFFFFFFFF)
                if self._log:
                    self._log.info("DLT645 从站事件记录已清零")
                return {"ok": True, "message": "事件记录已清零"}
        except Exception as e:
            if self._log:
                self._log.error(f"DLT645 从站命令执行失败: {e}")
            return {"ok": False, "message": f"命令执行失败: {e}"}

        return {"ok": False, "message": f"不支持的命令: {command}"}

    @property
    def server(self):
        """获取底层服务器对象"""
        return self._server

    def get_captured_messages(self, count: int = 100) -> list:
        """获取捕获的报文列表

        Returns:
            报文记录列表，每条记录包含 direction, hex_string, timestamp 等
        """
        if self._server and hasattr(self._server, "get_captured_messages"):
            messages = self._server.get_captured_messages(0)
            return self._capture_sequences.serialize(messages, count)
        return []

    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        if self._server and hasattr(self._server, "clear_captured_messages"):
            self._server.clear_captured_messages()
            self._capture_sequences.clear()

    def get_avg_time(self) -> dict:
        """获取平均收发时间"""
        if not self._server:
            return {}
        try:
            stats = self._server.get_message_capture_stats()
            pairs = self._server.get_captured_pairs()
            # 从配对中计算平均延迟
            complete_pairs = [p for p in pairs if p.is_complete() and p.round_trip_time is not None]
            pair_count = len(complete_pairs)
            avg_latency_ms = 0.0
            if pair_count > 0:
                total_rtt = sum(p.round_trip_time for p in complete_pairs)
                avg_latency_ms = round((total_rtt / pair_count) * 1000, 2)
            return {
                "tx_count": stats.get("tx_count", 0),
                "rx_count": stats.get("rx_count", 0),
                "total_count": stats.get("tx_count", 0) + stats.get("rx_count", 0),
                "pair_count": pair_count,
                "avg_latency_ms": avg_latency_ms,
            }
        except Exception:
            return {}


class DLT645ClientHandler(ClientHandler):
    """DLT645 客户端处理器

    作为主站（客户端）连接到远程电表，主动读取电表数据。
    支持 TCP 和 RTU（串口）两种连接方式。
    """

    def __init__(self, log=None):
        super().__init__()
        self._capture_sequences = _CaptureSequenceTracker()
        self._client = None  # AsyncMeterClientService 实例
        self._transport_client = None  # AsyncTcpClient / AsyncRtuClient 底层连接
        self._log = log
        self._meter_address: str = "000000000000"
        self._is_serial: bool = False  # 是否为串口模式
        self._loop = None  # 连接建立时的事件循环引用（供自动读取线程复用）

    def initialize(self, config: dict[str, Any]) -> None:
        """初始化 DLT645 客户端

        Args:
            config: 配置字典，包含:
                TCP 模式:
                    - ip: 服务器 IP
                    - port: 服务器端口（默认 8899）
                RTU（串口）模式:
                    - serial_port: 串口号（如 COM1 或 /dev/ttyUSB0）
                    - baudrate: 波特率（默认 9600）
                    - databits: 数据位（默认 8）
                    - stopbits: 停止位（默认 1）
                    - parity: 校验位（默认 "E" 偶校验）
                通用:
                    - meter_address: 电表地址（12位BCD码）
                    - timeout: 超时时间（默认 30）
        """
        self._config = config
        timeout = config.get("timeout", 3)  # 默认3秒超时，避免长时间阻塞
        runtime = config.get("runtime", {})
        timeout = runtime.get("command_timeout_ms", 3000) / 1000
        self._meter_address = config.get("meter_address", "000000000000")

        # 判断使用 TCP 还是 RTU 模式
        serial_port = config.get("serial_port")

        if serial_port:
            # RTU（串口）模式
            self._is_serial = True
            baudrate = config.get("baudrate", 9600)
            databits = config.get("databits", 8)
            stopbits = config.get("stopbits", 1)
            parity = config.get("parity", "E")

            self._client = AsyncMeterClientService.new_rtu_client(
                port=serial_port,
                baudrate=baudrate,
                databits=databits,
                stopbits=stopbits,
                parity=parity,
                timeout=timeout,
            )
        else:
            # TCP 模式
            self._is_serial = False
            ip = config.get("ip", "127.0.0.1")
            port = config.get("port", Config.DLT645_DEFAULT_PORT)

            self._client = AsyncMeterClientService.new_tcp_client(ip=ip, port=port, timeout=timeout)

        if self._client:
            # 设置电表地址（12位BCD码字符串）
            addr_str = str(self._meter_address).zfill(12)
            self._client.set_address(addr_str)
            # 保存底层传输客户端引用
            self._transport_client = self._client.client

            # 启用报文捕获
            if hasattr(self._client, "enable_message_capture"):
                self._client.enable_message_capture(queue_size=200)
            else:
                if self._log:
                    self._log.warning("DLT645 客户端不支持报文捕获")

    async def start(self) -> bool:
        """启动客户端（建立异步连接）"""
        import asyncio

        # 记录连接所在的事件循环：AsyncTcpClient/AsyncRtuClient 的底层连接
        # 绑定在此循环上，后续自动读取线程需复用该循环（见 device.update_data）。
        self._loop = asyncio.get_running_loop()
        return await self.connect()

    async def stop(self) -> bool:
        """停止客户端（断开连接）"""
        await self.disconnect()
        return True

    async def connect(self) -> bool:
        """连接到 DLT645 电表"""
        try:
            if self._client:
                result = await self._client.connect()
                if result:
                    self._is_running = True
                    mode = "串口" if self._is_serial else "TCP"
                    if self._log:
                        self._log.info(f"DLT645 客户端({mode})连接成功, 电表地址: {self._meter_address}")
                return result
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"连接 DLT645 电表失败: {e}")
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        if self._client:
            with contextlib.suppress(Exception):
                await self._client.disconnect()
            self._is_running = False

    def read_value(self, point: BasePoint) -> Any:
        """读取测点值（同步占位接口）

        dlt645 3.0.0 客户端为异步实现，网络读取请使用 read_value_async()。
        同步路径无网络请求能力，统一返回 None 表示读取失败。
        """
        if self._log:
            self._log.warning("DLT645 客户端 read_value 为同步占位接口，请改用 read_value_async() 读取")
        return None

    async def read_value_async(self, point: BasePoint) -> Any:
        """异步读取测点值

        从远程电表读取数据标识对应的值。
        根据 DI 前缀调用相应的 read_XX 方法。
        """
        if not self._client:
            return None

        # 每次读取先清空附加显示，避免残留上一次结果
        point._dlt645_display_extra = None

        try:
            # DLT645 使用数据标识 (DI) 读取
            di = point.address
            hex_addr = hex(di)[2:].zfill(8)
            prefix = hex_addr[:2]  # DI 前缀决定读取方法

            # 根据 DI 前缀选择读取方法
            data_item = None
            if prefix == "00":
                data_item = await self._client.read_00(di)  # 读取电能
            elif prefix == "01":
                data_item = await self._client.read_01(di)  # 读取最大需量
            elif prefix == "02":
                data_item = await self._client.read_02(di)  # 读取变量
            elif prefix == "03":
                data_item = await self._client.read_03(di)  # 读取事件记录
            elif prefix == "04":
                data_item = await self._client.read_04(di)  # 读取参变量
            else:
                if self._log:
                    self._log.warning(f"DLT645 客户端暂不支持 DI 前缀 {prefix} (addr: {hex_addr})")
                return None

            if data_item is None:
                # 超时、地址不匹配和电表异常响应都属于读取失败，不能用 0
                # 冒充成功值，否则前端会误以为只读到了一个数值。
                return None

            # 复合 DI（最大需量及其发生时间等）的完整显示值挂到测点，
            # 供表格"真实值"列逗号分隔展示；纯数值测点不设置，保持原有显示
            if _is_compound(data_item):
                display = _data_item_display(data_item, point)
                if display is not None:
                    point._dlt645_display_extra = display
            # 返回数值主值更新测点模型（point.value / real_value 只接受数值）
            return _primary_numeric(data_item, point)

        except Exception as e:
            if self._log:
                self._log.error(f"DLT645 读取数据失败: {e}")
            return None

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值（同步占位接口）

        dlt645 3.0.0 客户端为异步实现，网络写入请使用 write_value_async()。
        同步路径无网络请求能力，统一返回 False 表示写入失败。
        """
        if self._log:
            self._log.warning("DLT645 客户端 write_value 为同步占位接口，请改用 write_value_async() 写入")
        return False

    async def write_value_async(self, point: BasePoint, value: Any) -> bool:
        """异步写入测点值（发送命令）

        向远程电表写入数据。注意：大多数电表数据是只读的，
        只有 DI 前缀为 04 的参变量支持写入。
        """
        if not self._client:
            return False

        try:
            di = point.address
            hex_addr = hex(di)[2:].zfill(8)
            prefix = hex_addr[:2]

            # 只有参变量 (04) 支持写入
            if prefix == "04":
                # 客户端写入：将内部原始值换算为物理值发送
                real_to_send = value
                if isinstance(point, Yc):
                    real_to_send = value * point.mul_coe + point.add_coe

                # 写参变量需要密码，这里使用默认空密码
                result = await self._client.write_04(di, str(real_to_send), "00000000")
                return result is not None
            else:
                if self._log:
                    self._log.warning(f"DLT645 客户端只能写入参变量 (DI前缀04), 当前: {prefix}")
                return False

        except Exception as e:
            if self._log:
                self._log.error(f"DLT645 写入数据失败: {e}")
            return False

    def add_points(self, points: list[BasePoint]) -> None:
        """添加测点（DLT645 客户端按需读写，无需预先添加）"""
        pass

    def set_meter_address(self, address: str) -> None:
        """设置电表地址"""
        self._meter_address = address
        if self._client:
            self._client.set_address(address)

    async def send_command(self, command: str, params: dict | None = None) -> dict:
        """发送 DL/T645 特殊命令（主站功能）

        支持命令：
        - read_address: 读通讯地址
        - write_address: 写通讯地址 (params: address 12位数字)
        - broadcast_time_sync: 广播校时 (params: datetime 可选 ISO 字符串)
        - freeze: 冻结命令（瞬时广播冻结，无需应答）
        - change_baud_rate: 更改通信速率 (params: baud 1200/2400/4800/9600/19200)
        - change_password: 修改密码 (params: old_password, new_password 8位数字)
        - clear_demand: 最大需量清零 (params: password 8位数字, di 可选默认 0x01010000)
        - clear_meter: 电表清零 (params: password 8位数字)
        - clear_event: 事件清零 (params: password 8位数字, di 可选默认 FFFFFFFF)

        Returns:
            {"ok": bool, "message": str, "detail": dict | None}
        """
        params = params or {}
        if not self._client:
            return {"ok": False, "message": "DLT645 客户端未初始化"}

        try:
            if command == "read_address":
                item = await self._client.read_address()
                if item is None:
                    return {"ok": False, "message": "读通讯地址失败（无响应）"}
                detail = _data_item_detail(item)
                if self._log:
                    self._log.info(f"DLT645 读通讯地址成功: {detail}")
                return {
                    "ok": True,
                    "message": "读通讯地址成功",
                    "detail": detail,
                }

            if command == "write_address":
                from dlt645.common.transform import string_to_bcd

                address = str(params.get("address", "")).strip()
                if len(address) != 12 or not address.isdigit():
                    return {"ok": False, "message": "通讯地址必须为 12 位数字"}
                item = await self._client.write_address(string_to_bcd(address))
                if item is None:
                    return {"ok": False, "message": "写通讯地址失败（无响应）"}
                if self._log:
                    self._log.info(f"DLT645 写通讯地址成功: {address}")
                return {
                    "ok": True,
                    "message": "写通讯地址成功",
                    "detail": {"address": address},
                }

            if command == "broadcast_time_sync":
                dt = _parse_command_datetime(params.get("datetime"))
                ok = await self._client.broadcast_time_sync(dt)
                if not ok:
                    return {"ok": False, "message": "广播校时发送失败"}
                if self._log:
                    self._log.info(f"DLT645 广播校时: {dt:%Y-%m-%d %H:%M:%S}")
                return {
                    "ok": True,
                    "message": f"广播校时已发送 ({dt:%Y-%m-%d %H:%M:%S})",
                    "detail": {"datetime": dt.isoformat()},
                }

            if command == "freeze":
                # 瞬时广播冻结（MMDDhhmm 全为 99），无需应答
                item = await self._client.freeze(month=99, day=99, hour=99, minute=99, broadcast=True)
                if item is None:
                    return {"ok": False, "message": "冻结命令发送失败"}
                if self._log:
                    self._log.info("DLT645 瞬时广播冻结已发送")
                return {
                    "ok": True,
                    "message": "冻结命令已发送（瞬时广播冻结）",
                    "detail": _data_item_detail(item),
                }

            if command == "change_baud_rate":
                baud = int(params.get("baud", 9600))
                item = await self._client.change_baud_rate(baud)
                if item is None:
                    return {
                        "ok": False,
                        "message": f"更改通信速率失败（不支持 {baud} bps 或从站无响应）",
                    }
                if self._log:
                    self._log.info(f"DLT645 更改通信速率为: {baud} bps")
                return {
                    "ok": True,
                    "message": f"通信速率已更改为 {baud} bps",
                    "detail": {"baud": baud},
                }

            if command == "change_password":
                old_password = str(params.get("old_password", "")).strip()
                new_password = str(params.get("new_password", "")).strip()
                if len(old_password) != 8 or not old_password.isdigit():
                    return {"ok": False, "message": "旧密码必须为 8 位数字"}
                if len(new_password) != 8 or not new_password.isdigit():
                    return {"ok": False, "message": "新密码必须为 8 位数字"}
                ok = await self._client.change_password(old_password, new_password)
                if not ok:
                    return {"ok": False, "message": "修改密码失败（旧密码错误或无响应）"}
                if self._log:
                    self._log.info("DLT645 修改密码成功")
                return {"ok": True, "message": "修改密码成功"}

            if command == "clear_demand":
                password = str(params.get("password", "")).strip()
                if len(password) != 8 or not password.isdigit():
                    return {"ok": False, "message": "密码必须为 8 位数字"}
                di = int(params.get("di", 0x01010000))
                item = await self._client.clear_demand(di, password)
                if item is None:
                    return {"ok": False, "message": "最大需量清零失败（密码错误或无响应）"}
                if self._log:
                    self._log.info(f"DLT645 最大需量清零成功: DI={hex(di)}")
                return {
                    "ok": True,
                    "message": "最大需量清零成功",
                    "detail": {"di": hex(di)},
                }

            if command == "clear_meter":
                password = str(params.get("password", "")).strip()
                if len(password) != 8 or not password.isdigit():
                    return {"ok": False, "message": "密码必须为 8 位数字"}
                item = await self._client.clear_meter(password)
                if item is None:
                    return {"ok": False, "message": "电表清零失败（密码错误或无响应）"}
                if self._log:
                    self._log.info("DLT645 电表清零成功")
                return {"ok": True, "message": "电表清零成功"}

            if command == "clear_event":
                password = str(params.get("password", "")).strip()
                if len(password) != 8 or not password.isdigit():
                    return {"ok": False, "message": "密码必须为 8 位数字"}
                di = int(params.get("di", 0xFFFFFFFF))
                item = await self._client.clear_event(password, di=di)
                if item is None:
                    return {"ok": False, "message": "事件清零失败（密码错误或无响应）"}
                if self._log:
                    self._log.info(f"DLT645 事件清零成功: DI={hex(di)}")
                return {
                    "ok": True,
                    "message": "事件清零成功",
                    "detail": {"di": hex(di)},
                }
        except Exception as e:
            if self._log:
                self._log.error(f"DLT645 命令执行失败: {e}")
            return {"ok": False, "message": f"命令执行失败: {e}"}

        return {"ok": False, "message": f"不支持的命令: {command}"}

    @property
    def client(self):
        """获取底层客户端对象"""
        return self._client

    def get_captured_messages(self, count: int = 100) -> list:
        """获取捕获的报文列表

        Returns:
            报文记录列表，每条记录包含 direction, hex_string, timestamp 等
        """
        if self._client and hasattr(self._client, "get_captured_messages"):
            messages = self._client.get_captured_messages(0)
            return self._capture_sequences.serialize(messages, count)
        return []

    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        if self._client and hasattr(self._client, "clear_captured_messages"):
            self._client.clear_captured_messages()
            self._capture_sequences.clear()

    def get_avg_time(self) -> dict:
        """获取平均收发时间"""
        if not self._client:
            return {}
        try:
            stats = self._client.get_message_capture_stats()
            pairs = self._client.get_captured_pairs()
            # 从配对中计算平均延迟
            complete_pairs = [p for p in pairs if p.is_complete() and p.round_trip_time is not None]
            pair_count = len(complete_pairs)
            avg_latency_ms = 0.0
            if pair_count > 0:
                total_rtt = sum(p.round_trip_time for p in complete_pairs)
                avg_latency_ms = round((total_rtt / pair_count) * 1000, 2)
            return {
                "tx_count": stats.get("tx_count", 0),
                "rx_count": stats.get("rx_count", 0),
                "total_count": stats.get("tx_count", 0) + stats.get("rx_count", 0),
                "pair_count": pair_count,
                "avg_latency_ms": avg_latency_ms,
            }
        except Exception:
            return {}
