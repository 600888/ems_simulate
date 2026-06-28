"""
IEC104 协议处理器
支持 IEC104 服务端和客户端
"""

from typing import Any

import c104

from src.config.config import Config
from src.device.protocol.base_handler import ClientHandler, ServerHandler
from src.enums.point_data import Yc, Yk, Yt, Yx
from src.enums.points.base_point import BasePoint
from src.enums.points.iec104_quality import (
    encode_quality_for_c104,
    supports_quality,
)
from src.enums.points.iec104_type import (
    decode_iec104_value,
    encode_iec104_value,
    resolve_iec104_type,
)


def _resolve_c104_type(point: BasePoint) -> c104.Type:
    """根据测点的 iec_type_id 解析 c104.Type 常量

    Args:
        point: 测点对象

    Returns:
        c104.Type 枚举值
    """
    iec_type = resolve_iec104_type(point.iec_type_id, point.frame_type)
    # c104 库使用 TypeID 字符串作为属性名映射到 c104.Type
    return getattr(c104.Type, iec_type.value)


class IEC104ServerHandler(ServerHandler):
    """IEC104 服务端处理器"""

    def __init__(self, log=None):
        super().__init__()
        self._server = None
        self._log = log
        # 命令点 IOA → BasePoint 映射，用于收到客户端命令后更新应用层点值
        self._command_point_map: dict[int, BasePoint] = {}

    def initialize(self, config: dict[str, Any]) -> None:
        """初始化 IEC104 服务器

        Args:
            config: 配置字典，包含:
                - ip: 监听 IP（默认 0.0.0.0）
                - port: 监听端口（默认 2404）
                - common_address: 站地址（默认 1）
        """
        from src.proto.iec104.iec104server import IEC104Server

        self._config = config
        ip = config.get("ip", Config.DEFAULT_IP)
        port = config.get("port", Config.IEC104_DEFAULT_PORT)
        common_address = config.get("common_address", 1)

        self._server: IEC104Server = IEC104Server(ip=ip, port=port, common_address=common_address)

    async def start(self) -> bool:
        """启动 IEC104 服务器"""
        try:
            if self._server:
                self._server.start()
                self._is_running = True
                return True
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"启动 IEC104 服务器失败: {e}")
            return False

    async def stop(self) -> bool:
        """停止 IEC104 服务器"""
        try:
            if self._server and hasattr(self._server, "stop"):
                self._server.stop()
                self._is_running = False
                return True
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"停止 IEC104 服务器失败: {e}")
            return False

    def read_value(self, point: BasePoint) -> Any:
        """读取测点值"""
        if self._server:
            return self._server.get_point_value(io_address=int(point.address), frame_type=point.frame_type)
        return 0

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值

        根据 IEC104 ASDU 类型对值进行编码后写入 c104 点：
        - 归一化类型 (M_ME_NA_1): 值需在 -1~+1 范围，使用 c104.NormalizedFloat
        - 标度化类型 (M_ME_NB_1): 值取整，使用 c104.Int16
        - 短浮点类型 (M_ME_NC_1): 保持 float

        同时写入品质描述符（OV/BL/SB/NT/IV）。
        """
        if self._server:
            # 获取要写入的物理值
            if isinstance(point, (Yc, Yt)):
                real_value = point.real_value
            elif isinstance(point, (Yx, Yk)):
                # 遥信/遥控: 直接用 bool/int
                self._server.set_point_value(
                    io_address=int(point.address),
                    value=bool(point.value),
                    frame_type=point.frame_type,
                )
                # 写入品质描述符
                if supports_quality(point.frame_type):
                    quality_int = encode_quality_for_c104(point.iec_quality, point.frame_type)
                    self._server.set_point_quality(
                        io_address=int(point.address),
                        quality=quality_int,
                        frame_type=point.frame_type,
                    )
                return True
            else:
                real_value = value

            # 根据 IEC104 类型编码值（返回 c104 原生类型）
            encoded_value = encode_iec104_value(real_value, point.iec_type_id)

            self._server.set_point_value(
                io_address=int(point.address),
                value=encoded_value,
                frame_type=point.frame_type,
            )
            # 写入品质描述符
            if supports_quality(point.frame_type):
                quality_int = encode_quality_for_c104(point.iec_quality, point.frame_type)
                self._server.set_point_quality(
                    io_address=int(point.address),
                    quality=quality_int,
                    frame_type=point.frame_type,
                )
            return True
        return False

    async def read_value_async(self, point: BasePoint) -> Any:
        """异步读取测点值"""
        return self.read_value(point)

    async def write_value_async(self, point: BasePoint, value: Any) -> bool:
        """异步写入测点值"""
        return self.write_value(point, value)

    def add_points(self, points: list[BasePoint]) -> None:
        """添加测点到 IEC104 服务器"""
        if not self._server:
            return

        for point in points:
            frame_type = point.frame_type
            point_type = _resolve_c104_type(point)

            if frame_type in (0, 1):  # 遥测/遥信 → 监控点
                self._server.add_monitoring_point(
                    io_address=point.address,
                    point_type=point_type,
                    report_ms=1000,  # 自动上报间隔 1 秒
                )
            elif frame_type in (2, 3):  # 遥控/遥调 → 命令点
                self._server.add_command_point(
                    io_address=point.address,
                    point_type=point_type,
                )
                # 建立 IOA → BasePoint 映射，用于命令接收后同步更新应用层值
                self._command_point_map[int(point.address)] = point

        # 注册命令接收回调（每次 add_points 时更新）
        self._server.set_on_command_callback(self._on_command_received)

    def _on_command_received(self, io_address: int, value, point_type) -> None:
        """
        当服务端收到客户端发送的遥控/遥调命令时，同步更新应用层测点值。

        Args:
            io_address: 信息对象地址(IOA)
            value: 接收到的命令值（c104 原生类型）
            point_type: c104 点类型
        """
        point = self._command_point_map.get(io_address)
        if point is None:
            if self._log:
                self._log.warning(f"收到IOA {io_address} 的命令，但未找到对应的应用层测点")
            return

        try:
            # c104 对不同类型返回不同的值对象，转换为 Python 原生类型
            if isinstance(point, (Yx, Yk)):
                new_value = int(bool(value))
            elif point_type in (c104.Type.C_SE_NA_1, c104.Type.C_SE_TA_1):
                # 归一化值有 16-bit 精度损失（如 1.0→0.999969），四舍五入恢复
                new_value = round(float(value))
            else:
                new_value = float(value)

            # 通过 set_real_value 更新（会触发 value setter 和变更追踪）
            if point.set_real_value(new_value):
                if self._log:
                    self._log.info(f"服务端收到命令并更新测点 {point.code}(IOA={io_address}): {new_value}")
            else:
                if self._log:
                    self._log.warning(f"服务端收到命令但测点 {point.code} 值 {new_value} 超出允许范围")
        except Exception as e:
            if self._log:
                self._log.error(f"更新命令接收后的测点值失败: {e}")

    def get_value_by_address(self, func_code: int, slave_id: int, address: int) -> Any:
        """根据地址获取值"""
        if self._server:
            return self._server.get_point_value(io_address=address, frame_type=0)
        return 0

    def set_value_by_address(self, func_code: int, slave_id: int, address: int, value: Any) -> None:
        """根据地址设置值"""
        if self._server:
            self._server.set_point_value(io_address=address, value=value, frame_type=0)

    @property
    def server(self):
        """获取底层服务器对象"""
        return self._server

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取捕获的报文列表"""
        if self._server and hasattr(self._server, "get_captured_messages"):
            return self._server.get_captured_messages(limit)
        return []

    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        if self._server and hasattr(self._server, "clear_captured_messages"):
            self._server.clear_captured_messages()

    def get_avg_time(self) -> dict:
        """获取平均收发时间"""
        if self._server and hasattr(self._server, "message_capture"):
            return self._server.message_capture.get_avg_time()
        return {}


class IEC104ClientHandler(ClientHandler):
    """IEC104 客户端处理器"""

    def __init__(self, log=None):
        super().__init__()
        self._client = None
        self._log = log

    def initialize(self, config: dict[str, Any]) -> None:
        """初始化 IEC104 客户端

        Args:
            config: 配置字典，包含:
                - ip: 服务器 IP
                - port: 服务器端口（默认 2404）
                - common_address: 站地址（默认 1）
        """
        from src.proto.iec104.iec104client import IEC104Client

        self._config = config
        ip = config.get("ip", "127.0.0.1")
        port = config.get("port", Config.IEC104_DEFAULT_PORT)
        common_address = config.get("common_address", 1)

        self._client = IEC104Client(ip=ip, port=port, common_address=common_address)

    async def start(self) -> bool:
        """启动客户端（连接服务器）"""
        return await self.connect()

    async def stop(self) -> bool:
        """停止客户端（断开连接）"""
        self.disconnect()
        return True

    async def connect(self) -> bool:
        """连接到 IEC104 服务器"""
        try:
            if self._client:
                is_connected = await self._client.connect()
                self._is_running = is_connected
                return is_connected
            return False
        except Exception as e:
            if self._log:
                self._log.error(f"连接 IEC104 服务器失败: {e}")
            return False

    def disconnect(self) -> None:
        """断开连接"""
        if self._client:
            self._client.disconnect()
            self._is_running = False

    @property
    def is_running(self) -> bool:
        """检测客户端的真实连接状态

        重写父类方法，实时检测连接状态。
        当服务端主动断开时，这个属性能反映真实状态。
        注意：不再缓存断开状态到 _is_running，避免连接恢复后仍然无法读取数据。
        """
        if not self._is_running:
            return False

        if not self._client:
            return False

        # 实时检查 IEC104Client 的连接状态（不缓存断开状态）
        if hasattr(self._client, "is_connected") and not self._client.is_connected:
            return False

        # 实时检查 c104 station 的连接状态
        if hasattr(self._client, "station") and self._client.station:
            if hasattr(self._client.station, "is_connected") and not self._client.station.is_connected:
                return False

        return True

    def read_value(self, point: BasePoint) -> Any:
        """读取测点值

        读取 c104 点的值，c104 库已内部完成类型解码：
        - 归一化类型: float(point.value) 返回 -1~+1 范围的浮点数
        - 标度化类型: float(point.value) 返回标度值
        - 短浮点类型: float(point.value) 返回浮点数

        对于遥测点(Yc)，c104 返回的值即为协议物理值，
        需要通过系数换算为内部存储值，使得 real_value 正确。
        """
        # 检查客户端是否已连接（使用 is_running 属性实时检测）
        if not self._client or not self.is_running:
            self._log.error("IEC104 客户端未连接")
            return None

        # IEC104 客户端通过 read_point 获取值
        # c104 库已内部完成类型解码，float() 即可得到物理值
        c104_value = self._client.read_point(io_address=int(point.address), frame_type=point.frame_type)

        # 同步品质描述符（c104.Point.quality 在服务端上报时自动更新）
        # c104 库的品质位编码与应用层不同，需要转换
        try:
            c104_point = self._client.station.get_point(io_address=int(point.address))
            if c104_point and hasattr(c104_point, "quality") and c104_point.quality is not None:
                from src.enums.points.iec104_quality import decode_quality_from_c104

                qd = decode_quality_from_c104(c104_point, point.frame_type)
                point.iec_quality = qd
        except Exception:
            pass

        if c104_value is None:
            self._log.error("IEC104 客户端读取测点值失败")
            return None

        # 对于遥测点，c104 返回的值是协议层物理值
        # 需要通过 mul_coe/add_coe 反向换算为内部存储值
        # 使得: real_value = value * mul_coe + add_coe = c104_value
        # 即: value = (c104_value - add_coe) / mul_coe
        if isinstance(point, Yc):
            decoded_val = decode_iec104_value(c104_value, point.iec_type_id)
            try:
                # 计算内部存储值，使得 real_value = value * mul_coe + add_coe = decoded_val
                internal_value = (decoded_val - point.add_coe) / point.mul_coe
                # 对于浮点解码模式，保留浮点精度；否则取整
                from src.enums.modbus_register import Decode

                info = Decode.get_info(point.decode)
                if info.is_float:
                    return float(internal_value)
                return int(round(internal_value))
            except (ZeroDivisionError, TypeError):
                self._log.error(f"IEC104 客户端读取测点值失败，系数计算失败，地址: {point.address}")
                return None
        return c104_value

    def write_value(self, point: BasePoint, value: Any) -> bool:
        """写入测点值（发送命令）

        根据 IEC104 ASDU 类型对值进行编码后写入：
        - 归一化类型: 使用 c104.NormalizedFloat
        - 标度化类型: 使用 c104.Int16
        - 短浮点类型: 直接 float
        """
        if not self._client or not self.is_running:
            return False

        # 客户端写入：将内部原始值换算为物理值发送给外部设备
        try:
            if isinstance(point, (Yc, Yt)):
                real_to_send = value * point.mul_coe + point.add_coe
                # 根据 IEC104 类型编码值（返回 c104 原生类型）
                encoded_value = encode_iec104_value(real_to_send, point.iec_type_id)
                return self._client.write_point(
                    io_address=int(point.address), value=encoded_value, frame_type=point.frame_type
                )
            elif isinstance(point, (Yx, Yk)):
                return self._client.write_point(
                    io_address=int(point.address), value=bool(value), frame_type=point.frame_type
                )
        except Exception as e:
            self._log.error(f"IEC104 客户端写入失败: {e}")
            return False

        return False

    async def read_value_async(self, point: BasePoint) -> Any:
        """异步读取测点值"""
        return self.read_value(point)

    async def write_value_async(self, point: BasePoint, value: Any) -> bool:
        """异步写入测点值"""
        return self.write_value(point, value)

    def add_points(self, points: list[BasePoint]) -> None:
        """添加测点到 IEC104 客户端"""
        if not self._client:
            return

        for point in points:
            point_type = _resolve_c104_type(point)
            self._client.add_point(
                io_address=int(point.address),
                point_type=point_type,
            )

    @property
    def client(self):
        """获取底层客户端对象"""
        return self._client

    def get_captured_messages(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取捕获的报文列表"""
        if self._client and hasattr(self._client, "get_captured_messages"):
            return self._client.get_captured_messages(limit)
        return []

    def clear_captured_messages(self) -> None:
        """清空捕获的报文"""
        if self._client and hasattr(self._client, "clear_captured_messages"):
            self._client.clear_captured_messages()

    def get_avg_time(self) -> dict:
        """获取平均收发时间"""
        if self._client and hasattr(self._client, "message_capture"):
            return self._client.message_capture.get_avg_time()
        return {}
