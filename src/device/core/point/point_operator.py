"""
测点操作器模块
负责测点的增删改查、值读取/写入、元数据编辑等操作。
"""

from __future__ import annotations

from copy import copy
import struct
from threading import RLock
from typing import TYPE_CHECKING

from src.data.dao.channel_dao import ChannelDao
from src.data.dao.point_dao import PointDao
from src.data.service.point_service import PointService
from src.data.service.yc_service import YcService
from src.data.service.yk_service import YkService
from src.data.service.yt_service import YtService
from src.data.service.yx_service import YxService
from src.device.protocol.base_handler import ClientHandler, ServerHandler
from src.enums.modbus_def import ProtocolType
from src.enums.modbus_register import Decode
from src.enums.point_data import BasePoint, SimulateMethod, Yc, Yk, Yt, Yx
from src.enums.points.change_tracker import ChangeSource, track_change
from src.enums.points.iec104_command_mode import IEC104CommandMode

if TYPE_CHECKING:
    from src.device.core.device import Device


def _read_result(point: BasePoint) -> float | str:
    """读取结果：DLT645 复合 DI（如最大需量及其发生时间）优先返回逗号分隔
    显示串，否则返回数值主值。"""
    display_extra = getattr(point, "_dlt645_display_extra", None)
    if display_extra is not None:
        return display_extra
    return float(point.value) if getattr(point, "bit", None) is not None else point.real_value


# Modbus 客户端协议集合: 这些协议下 Yc/Yx 带有 func_code=01/03 的测点允许客户端写入
_MODBUS_PROTOCOLS = frozenset(
    {
        ProtocolType.ModbusTcpClient,
        ProtocolType.ModbusTcpServer,
        ProtocolType.ModbusRtu,
        ProtocolType.ModbusRtuClient,
        ProtocolType.ModbusRtuServer,
        ProtocolType.ModbusRtuOverTcp,
        ProtocolType.ModbusUdp,
    }
)


class PointOperator:
    """测点操作器

    处理测点的增删改查操作，协调内存状态、协议处理器和数据库的一致性。
    """

    def __init__(self, device: Device) -> None:
        self._device = device
        self._metadata_lock = RLock()

    @property
    def _pm(self):
        """获取测点管理器"""
        return self._device.point_manager

    @property
    def _handler(self):
        """获取协议处理器"""
        return self._device.protocol_handler

    @property
    def _log(self):
        """获取日志器"""
        return self._device.log

    def _get_client_info(self) -> str:
        """获取作为客户端时的真实远程服务地址(IP:Port 或 串口号)"""
        if isinstance(self._handler, ClientHandler):
            if self._device.serial_port:
                return self._device.serial_port
            return f"{self._device.ip}:{self._device.port}"
        return ""

    def _get_channel_id(self) -> int:
        """获取当前设备对应的通道ID"""
        channel = ChannelDao.get_channel_by_code(self._device.name)
        if not channel:
            channels = ChannelDao.get_all_channels()
            channel = next((c for c in channels if c["name"] == self._device.name), None)
        if channel:
            return channel["id"]
        raise ValueError(f"找不到设备 {self._device.name} 的通道信息")

    # ===== 测点值读写 =====

    def reset_values(self) -> None:
        """清零所有测点的原始值，并同步服务端用于应答的数据。"""
        from src.device.protocol.iec61850_handler import IEC61850ServerHandler

        points = self._pm.get_all_points()
        if not points:
            return

        handler = self._handler
        sync_point = handler.reset_point_value if isinstance(handler, ServerHandler) else None
        # IEC 61850 在一个数据模型事务中清零，避免每个点分别触发报告。
        if isinstance(handler, IEC61850ServerHandler):
            sync_point = None
            if handler.is_running and not handler.write_values_batch([(point, 0) for point in points]):
                raise ValueError("IEC 61850 服务端测点清零失败")

        failures = 0
        with track_change(ChangeSource.MANUAL, "重置测点值"):
            for point in points:
                try:
                    if sync_point is not None and not sync_point(point):
                        raise ValueError("协议层写入失败")
                    point.value = 0
                except Exception as exc:
                    failures += 1
                    self._log.warning(f"从站 {point.rtu_addr} 测点 {point.code or point.address} 清零失败: {exc}")
        if failures:
            raise ValueError(f"{failures} 个测点清零失败，请查看设备日志")

    def _set_real_value(self, point: BasePoint, real_value) -> bool:
        """An IEC enum ordinal must bypass binary Yx/Yk and analogue scaling rules."""
        from src.device.protocol.iec61850_handler import get_iec61850_value_model

        model = get_iec61850_value_model(self._handler)
        attribute = model.find_attribute(str(point.address), point.fc) if model is not None else None
        if attribute is not None and attribute.b_type.upper() == "ENUM":
            model.validate_enum_value(str(point.address), real_value, point.fc)
            point.value = real_value
            return True
        return point.set_real_value(real_value)

    def _allows_iec61850_direct_write(self, point: BasePoint) -> bool:
        from src.device.protocol.iec61850_handler import IEC61850ClientHandler

        return isinstance(self._handler, IEC61850ClientHandler) and point.fc in {
            "SP",
            "SE",
            "SV",
            "CF",
            "DC",
            "SG",
            "BL",
            "EX",
        }

    def edit_value(
        self,
        point_code: str,
        real_value: float,
        source: ChangeSource | None = None,
        detail: str | None = None,
        slave_id: int | None = None,
    ) -> bool:
        """编辑测点值，失败时抛出异常以便上层返回具体原因

        Args:
            point_code: 测点编码
            real_value: 真实值
            source: 变更来源
            detail: 变更详情
            slave_id: 从机 ID，不同从站编码相同时用于精确定位测点
        """
        point = self._pm.get_point_by_code(point_code, slave_id)
        if not point:
            raise ValueError(f"未找到测点: {point_code}")

        if (
            isinstance(self._handler, ClientHandler)
            and isinstance(point, (Yc, Yx))
            and getattr(point, "fc", "") != "CO"
            and not self._allows_iec61850_direct_write(point)
        ):
            # Modbus 协议: func_code=01(读线圈)/03(读保持寄存器) 的 Yc/Yx 允许客户端写入
            if not (self._device.protocol_type in _MODBUS_PROTOCOLS and getattr(point, "func_code", None) in (1, 3)):
                raise ValueError("作为客户端时，只允许对遥控(Yk)和遥调(Yt)类测点进行写入操作")

        # 如果未指定来源，默认使用 MANUAL
        effective_source = source or ChangeSource.MANUAL
        effective_detail = detail or f"手动设置 {point_code}={real_value}"

        with track_change(effective_source, effective_detail):
            if not self._set_real_value(point, real_value):
                raise ValueError(f"测点 {point_code} 值 {real_value} 超出允许范围")

            if self._handler:
                try:
                    result = self._handler.write_value(point, point.value)
                except Exception as e:
                    raise ValueError(f"测点 {point_code} 写入失败: {e}") from e
                if not result:
                    protocol_detail = getattr(self._handler, "last_error", None)
                    detail = f": {protocol_detail}" if protocol_detail else "，请检查配置或物理连接"
                    raise ValueError(f"测点 {point_code} 协议写入失败{detail}")
                # self._log.debug(f"测点 {point_code} 写入成功: {real_value}")
                return result
            else:
                raise SystemError(f"测点 {point_code} 协议处理器未配置，无法写入")

    async def edit_value_async(
        self,
        point_code: str,
        real_value: float,
        source: ChangeSource | None = None,
        detail: str | None = None,
        slave_id: int | None = None,
    ) -> bool:
        """异步编辑测点值，失败时抛出异常以便上层返回具体原因

        Args:
            point_code: 测点编码
            real_value: 真实值
            source: 变更来源
            detail: 变更详情
            slave_id: 从机 ID，不同从站编码相同时用于精确定位测点
        """
        point = self._pm.get_point_by_code(point_code, slave_id)
        if not point:
            raise ValueError(f"未找到测点: {point_code}")

        if (
            isinstance(self._handler, ClientHandler)
            and isinstance(point, (Yc, Yx))
            and getattr(point, "fc", "") != "CO"
            and not self._allows_iec61850_direct_write(point)
        ):
            # Modbus 协议: func_code=01(读线圈)/03(读保持寄存器) 的 Yc/Yx 允许客户端写入
            if not (self._device.protocol_type in _MODBUS_PROTOCOLS and getattr(point, "func_code", None) in (1, 3)):
                raise ValueError("作为客户端时，只允许对遥控(Yk)和遥调(Yt)类测点进行操作")

        # 如果未指定来源，默认使用 MANUAL
        effective_source = source or ChangeSource.MANUAL
        effective_detail = detail or f"手动设置 {point_code}={real_value}"

        with track_change(effective_source, effective_detail):
            if not self._set_real_value(point, real_value):
                self._log.error(f"测点 {point_code} 值 {real_value} 超出允许范围")
                raise ValueError(f"测点 {point_code} 值 {real_value} 超出允许范围")

            if self._handler:
                try:
                    result = await self._handler.write_value_async(point, point.value)
                except Exception as e:
                    self._log.error(f"测点 {point_code} 写入失败: {e}")
                    raise ValueError(f"测点 {point_code} 写入失败: {e}") from e
                if not result:
                    protocol_detail = getattr(self._handler, "last_error", None)
                    detail = f": {protocol_detail}" if protocol_detail else "，请检查配置或物理连接"
                    self._log.error(f"测点 {point_code} 协议写入失败{detail}")
                    raise ValueError(f"测点 {point_code} 协议写入失败{detail}")
                self._log.info(f"测点 {point_code} 写入成功: {real_value}")
                return result
            else:
                self._log.error(f"测点 {point_code} 协议处理器未配置，无法写入")
                raise ValueError(f"测点 {point_code} 协议处理器未配置，无法写入")

    def read_single_point(self, point_code: str, slave_id: int | None = None) -> float | str | None:
        """读取单个测点的值

        Args:
            point_code: 测点编码
            slave_id: 从机 ID，不同从站编码相同时用于精确定位测点

        Returns:
            读取成功返回数值；DLT645 复合 DI 返回完整显示字符串；失败返回 None
        """
        point = self._pm.get_point_by_code(point_code, slave_id)
        if not point:
            self._log.error(f"{self._device.name} 未找到测点: {point_code}")
            return None

        if not self._handler:
            return None

        try:
            value = self._handler.read_value(point)
            if value is not None:
                with track_change(ChangeSource.CLIENT_READ, f"单点读取 {point_code}", self._get_client_info()):
                    point.value = value
                point.is_valid = True
                self._log.info(f"读取测点 {point_code} 成功: {value}")
                return _read_result(point)
            else:
                point.is_valid = False
                self._log.info(f"读取测点 {point_code} 失败: {value}")
        except Exception as e:
            self._log.error(f"读取测点 {point_code} 失败: {e}")
            point.is_valid = False
            raise ValueError(f"读取测点 {point_code} 失败: {e}") from e

    async def read_single_point_async(self, point_code: str, slave_id: int | None = None) -> float | str | None:
        """异步读取单个测点的值（读取本地缓存，不发送网络请求）

        Args:
            point_code: 测点编码
            slave_id: 从机 ID，不同从站编码相同时用于精确定位测点

        Returns:
            读取成功返回数值；DLT645 复合 DI 返回完整显示字符串；失败返回 None
        """
        point = self._pm.get_point_by_code(point_code, slave_id)
        if not point:
            self._log.error(f"{self._device.name} 未找到测点: {point_code}")
            return None

        if not self._handler:
            return None

        try:
            value = await self._handler.read_value_async(point)
            if value is not None:
                with track_change(ChangeSource.CLIENT_READ, f"异步单点读取 {point_code}", self._get_client_info()):
                    point.value = value
                point.is_valid = True
                self._log.info(f"异步读取测点 {point_code} 成功: {value}")
                return _read_result(point)
            else:
                point.is_valid = False
                self._log.info(f"异步读取测点 {point_code} 失败: {value}")
        except Exception as e:
            self._log.error(f"异步读取测点 {point_code} 失败: {e}")
            point.is_valid = False

        return None

    async def active_read_single_point_async(self, point_code: str, slave_id: int | None = None) -> float | str | None:
        """主动读取单个测点的值（发送网络请求获取最新值）

        与 read_single_point_async() 不同，此方法会向远程服务器发送
        网络请求（如 IEC104 的 C_RD_NA_1 或总召唤），而非仅读取本地缓存。

        Args:
            point_code: 测点编码
            slave_id: 从机 ID，不同从站编码相同时用于精确定位测点

        Returns:
            读取成功返回数值；DLT645 复合 DI 返回完整显示字符串；失败返回 None
        """
        from src.device.protocol.iec104_handler import IEC104ClientHandler

        point = self._pm.get_point_by_code(point_code, slave_id)
        if not point:
            self._log.error(f"{self._device.name} 未找到测点: {point_code}")
            return None

        if not self._handler:
            return None

        try:
            # IEC104 / DNP3 客户端使用专门的主动读取方法（发送网络请求获取最新值）
            if isinstance(self._handler, IEC104ClientHandler) or hasattr(self._handler, "active_read_value_async"):
                value = await self._handler.active_read_value_async(point)
            else:
                # 其他协议回退到普通异步读取
                value = await self._handler.read_value_async(point)

            if value is not None:
                with track_change(ChangeSource.CLIENT_READ, f"主动单点读取 {point_code}", self._get_client_info()):
                    point.value = value
                point.is_valid = True
                self._log.info(f"主动读取测点 {point_code} 成功: {value}")
                return _read_result(point)
            else:
                point.is_valid = False
                self._log.info(f"主动读取测点 {point_code} 失败")
        except Exception as e:
            self._log.error(f"主动读取测点 {point_code} 失败: {e}")
            point.is_valid = False

        return None

    async def read_metadata_async(self, point_code: str, slave_id: int | None = None) -> dict:
        """异步读取测点的品质(q)与时标(t)元数据"""
        if not self._handler:
            return {"quality": {}, "timestamp": {}}

        if not hasattr(self._handler, "read_metadata_async"):
            self._log.debug(f"协议处理器不支持元数据读取: {point_code}")
            return {"quality": {}, "timestamp": {}}

        point = self._pm.get_point_by_code(point_code, slave_id)
        if point is not None:
            return await self._handler.read_metadata_async(point)

        # point_code 可能是完整 DA 地址或 DO 引用，直接传给客户端
        from src.enums.points.base_point import BasePoint

        temp_point = BasePoint()
        temp_point.address = point_code
        temp_point.fc = ""
        return await self._handler.read_metadata_async(temp_point)

    # ===== 测点元数据编辑 =====

    def edit_metadata(self, point_code: str, metadata: dict) -> bool:
        """保存配置并同步实际负责收发报文的测点定义。"""
        with self._metadata_lock:
            point = self._pm.get_point_by_code(point_code)
            if point is None:
                raise ValueError(f"未找到测点: {point_code}")
            previous = copy(point)
            updated = copy(point)
            updated._is_updating = False
            updated.is_send_signal = False
            updated.disable_change_tracking()
            try:
                changes, original = self._prepare_metadata(updated, metadata)
            except (struct.error, OverflowError) as exc:
                raise ValueError("当前测点值超出新解析码的范围") from exc
            if not changes:
                return True

            channel_id = self._get_channel_id()
            if not PointService.update_point_metadata(point_code, changes, channel_id):
                return False

            # 保留原对象及其模拟配置、事件订阅和变更历史。
            fields = {
                name: value
                for name, value in vars(updated).items()
                if name not in {"is_send_signal", "_change_tracking_enabled", "_is_updating"}
                and vars(previous).get(name) != value
            }
            vars(point).update(fields)
            try:
                handler = self._handler
                sync_definition = getattr(handler, "update_point_definition", None)
                if sync_definition is not None:
                    sync_definition(point, previous)
                elif handler and isinstance(point, Yt) and point.value != previous.value:
                    if not isinstance(handler, ClientHandler) and not handler.write_value(point, point.value):
                        raise ValueError("遥调值同步失败")
            except Exception as exc:
                for name in fields:
                    if name in vars(previous):
                        vars(point)[name] = vars(previous)[name]
                    else:
                        vars(point).pop(name, None)
                if not PointService.update_point_metadata(updated.code, original, channel_id):
                    raise RuntimeError("协议属性同步失败，且无法恢复数据库中的旧属性") from exc
                raise ValueError(f"测点 {point_code} 的协议属性同步失败: {exc}") from exc

            if (point.rtu_addr, point.code) != (previous.rtu_addr, previous.code):
                self._pm.reindex_point(point, previous.rtu_addr, previous.code)
            return True

    def _prepare_metadata(self, point: BasePoint, metadata: dict) -> tuple[dict, dict]:
        """在不通知任何协议回调的副本上转换和验证属性。"""
        changes = {}
        original = {}

        def update(key, value, attr=None):
            attr = attr or key
            old = getattr(point, attr, None)
            if value == old:
                return
            setattr(point, attr, value)
            changes[key] = getattr(point, attr)
            original[key] = old

        for key in ("name", "code"):
            if metadata.get(key):
                update(key, metadata[key])
        if metadata.get("rtu_addr") not in (None, ""):
            slave_id = int(metadata["rtu_addr"])
            if slave_id != point.rtu_addr and slave_id not in self._pm.slave_id_list:
                raise ValueError(f"从站 {slave_id} 不存在")
            update("rtu_addr", slave_id)
        if metadata.get("reg_addr") not in (None, ""):
            address = str(metadata["reg_addr"]).strip()
            if isinstance(point.address, str):
                if address != point.address:
                    raise ValueError("模型测点地址由协议模型管理")
            else:
                value = int(address, 16 if address.lower().startswith("0x") else 10)
                if value < 0:
                    raise ValueError("测点地址不能小于 0")
                if value != point.address:
                    original["reg_addr"] = point.hex_address
                    point.address = value
                    changes["reg_addr"] = point.hex_address
        if metadata.get("func_code") not in (None, ""):
            update("func_code", int(metadata["func_code"]))
        if metadata.get("decode_code"):
            update("decode_code", Decode.normalize(metadata["decode_code"]), "decode")
        if isinstance(point, (Yk, Yx)) and "bit" in metadata:
            bit = metadata["bit"]
            bit = int(bit) if bit not in (None, "") else None
            if bit is not None and not 0 <= bit <= 31:
                raise ValueError("位偏移必须在 0 到 31 之间")
            update("bit", bit)

        if isinstance(point, (Yc, Yt)):
            current_real_value = point.real_value
            for key in ("mul_coe", "add_coe"):
                if metadata.get(key) not in (None, ""):
                    update(key, float(metadata[key]))
            if "mul_coe" in changes or "add_coe" in changes:
                if isinstance(point, Yt):
                    if point.mul_coe == 0 or not point.set_real_value(current_real_value):
                        raise ValueError("当前遥调值无法按新系数编码")
                else:
                    point.real_value = point.value * point.mul_coe + point.add_coe

        if "iec_type_id" in metadata:
            from src.enums.points.iec104_type import IEC104_TYPE_REGISTRY

            type_id = metadata["iec_type_id"] or None
            if type_id is not None:
                info = IEC104_TYPE_REGISTRY.get(type_id)
                if info is None or info.frame_type != point.frame_type:
                    raise ValueError("ASDU 类型不适用于当前测点类型")
            update("iec_type_id", type_id)
        if "iec_quality" in metadata:
            update("iec_quality", int(metadata["iec_quality"] or 0), "iec_quality_value")
        if "iec_command_mode" in metadata:
            if not isinstance(point, (Yk, Yt)) or self._device.protocol_type not in (
                ProtocolType.Iec104Server,
                ProtocolType.Iec104Client,
            ):
                raise ValueError("操作模式仅适用于 IEC104 遥控/遥调测点")
            update("iec_command_mode", IEC104CommandMode(metadata["iec_command_mode"]))
        if "dnp3_config" in metadata:
            from src.proto.dnp3.point_config import Dnp3PointConfig

            settings = metadata["dnp3_config"]
            if settings is not None:
                if not isinstance(settings, dict):
                    raise ValueError("DNP3 测点配置必须是对象")
                settings = {**(getattr(point, "dnp3_config", None) or {}), **settings}
            update("dnp3_config", Dnp3PointConfig.from_mapping(point.frame_type, settings).to_dict())
        return changes, original

    def edit_limit(self, point_code: str, min_value_limit: int, max_value_limit: int) -> bool:
        """编辑测点限值"""
        point = self._pm.get_point_by_code(point_code)
        if not point or not isinstance(point, (Yc, Yt)):
            return False

        if self._device.protocol_type in (ProtocolType.Dlt698Server, ProtocolType.Dlt698Client):
            from src.data.service.dlt698_service import Dlt698Service

            if not point.scalar:
                raise ValueError("此 Data 类型不支持标量限值")
            Dlt698Service.update_limits(self._device.device_id, point_code, min_value_limit, max_value_limit)
            point.min_value_limit, point.max_value_limit = min_value_limit, max_value_limit
            return True

        try:
            channel_id = self._get_channel_id()
            if not PointService.update_point_limit(
                self._device.name, point_code, min_value_limit, max_value_limit, channel_id
            ):
                return False
            point.min_value_limit, point.max_value_limit = min_value_limit, max_value_limit
            return True
        except Exception as e:
            self._log.error(f"更新测点限值失败: {e}")
            return False

    def get_point_data(self, point_code_list: list[str]) -> BasePoint | None:
        """获取测点"""
        for code in point_code_list:
            point = self._pm.get_point_by_code(code)
            if point:
                return point
        return None

    # ===== 动态测点操作 =====

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
            protocol_type = self._device.protocol_type

            # 1. 写入数据库
            db_point = PointDao.create_point(channel_id, frame_type, point_data)
            if not db_point:
                return False

            # 2. 转换为内存对象
            point: BasePoint
            slave_id = point_data.get("rtu_addr", 1)

            if frame_type == 0:  # 遥测
                point = YcService._create_point(db_point, protocol_type)
            elif frame_type == 1:  # 遥信
                point = YxService._create_point(db_point, protocol_type)
            elif frame_type == 2:  # 遥控
                point = YkService._create_point(db_point, protocol_type)
            elif frame_type == 3:  # 遥调
                point = YtService._create_point(db_point, protocol_type)
            else:
                return False

            # 3. 添加到测点管理器
            self._pm.add_point(slave_id, point)

            # 4. 添加到模拟控制器
            self._device.simulation_controller.add_point(point, SimulateMethod.Random, 1, is_running=True)

            # 5. 添加到协议处理器
            if self._handler:
                # IEC104 协议需要重新初始化
                if protocol_type in [
                    ProtocolType.Iec104Server,
                    ProtocolType.Iec104Client,
                    ProtocolType.Iec101Server,
                    ProtocolType.Iec101Client,
                ]:
                    self._device._reinit_protocol_for_iec104()
                else:
                    self._handler.add_points([point])

            self._log.info(f"动态添加测点成功: {point_data.get('code')}")
            return True

        except Exception as e:
            self._log.error(f"动态添加测点失败: {e}")
            return False

    def add_points_dynamic_batch(self, channel_id: int, frame_type: int, points_data_list: list[dict]) -> bool:
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
            from src.data.service.yk_service import YkService
            from src.data.service.yt_service import YtService
            from src.data.service.yx_service import YxService

            protocol_type = self._device.protocol_type

            # 1. 批量写入数据库
            db_points = PointDao.create_points_batch(channel_id, frame_type, points_data_list)
            if not db_points:
                return False

            memory_points = []

            # 2. 批量转换为内存对象
            for db_point in db_points:
                point: BasePoint | None = None
                slave_id = db_point.get("rtu_addr", 1)

                if frame_type == 0:
                    point = YcService._create_point(db_point, protocol_type)
                elif frame_type == 1:
                    point = YxService._create_point(db_point, protocol_type)
                elif frame_type == 2:
                    point = YkService._create_point(db_point, protocol_type)
                elif frame_type == 3:
                    point = YtService._create_point(db_point, protocol_type)
                else:
                    return False

                # 3. 添加到测点管理器
                if point:
                    self._pm.add_point(slave_id, point)

                # 4. 添加到模拟控制器
                self._device.simulation_controller.add_point(point, SimulateMethod.Random, 1, is_running=True)

                memory_points.append(point)

            # 5. 添加到协议处理器
            if self._handler:
                if protocol_type in [
                    ProtocolType.Iec104Server,
                    ProtocolType.Iec104Client,
                    ProtocolType.Iec101Server,
                    ProtocolType.Iec101Client,
                ]:
                    self._device._reinit_protocol_for_iec104()
                else:
                    self._handler.add_points(memory_points)

            self._log.info(f"动态批量添加 {len(memory_points)} 个测点成功")
            return True

        except Exception as e:
            self._log.error(f"动态批量添加测点失败: {e}")
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

            channel_id = self._get_channel_id()
            # 1. 从数据库删除
            if not PointDao.delete_point_by_code(point_code, channel_id):
                return False

            # 2. 从测点管理器删除
            point = self._pm.get_point_by_code(point_code)
            if point:
                # 从对应的列表中移除
                slave_id = point.rtu_addr
                if isinstance(point, Yc) and slave_id in self._pm.yc_dict:
                    self._pm.yc_dict[slave_id] = [p for p in self._pm.yc_dict[slave_id] if p.code != point_code]
                elif isinstance(point, Yx) and slave_id in self._pm.yx_dict:
                    self._pm.yx_dict[slave_id] = [p for p in self._pm.yx_dict[slave_id] if p.code != point_code]
                elif isinstance(point, Yk) and slave_id in self._pm.yk_dict:
                    self._pm.yk_dict[slave_id] = [p for p in self._pm.yk_dict[slave_id] if p.code != point_code]
                elif isinstance(point, Yt) and slave_id in self._pm.yt_dict:
                    self._pm.yt_dict[slave_id] = [p for p in self._pm.yt_dict[slave_id] if p.code != point_code]

                # 从索引中移除
                self._pm.remove_point_from_index(point_code, slave_id)

            # 3. IEC104 协议需要重新初始化（如果需要）
            if self._device.protocol_type in [
                ProtocolType.Iec104Server,
                ProtocolType.Iec104Client,
                ProtocolType.Iec101Server,
                ProtocolType.Iec101Client,
            ]:
                self._device._reinit_protocol_for_iec104()

            self._log.info(f"动态删除测点成功: {point_code}")
            return True

        except Exception as e:
            self._log.error(f"动态删除测点失败: {e}")
            return False

    # ===== 测点事件处理 =====

    def on_point_value_changed(self, sender, **extra) -> None:
        """处理测点值变化事件（联动触发）"""
        old_point = extra.get("old_point")
        related_point = extra.get("related_point")

        if not old_point or not related_point:
            return

        try:
            if old_point.related_value is None:
                change_value = old_point.value if isinstance(old_point, Yx) else old_point.real_value
            else:
                key = old_point.value if isinstance(old_point, Yx) else int(old_point.real_value)
                change_value = old_point.related_value.get(key)
                if change_value is None:
                    return

            self.edit_value(related_point.code, change_value)
        except Exception as e:
            self._log.error(f"处理点值变化事件失败: {e}")

    def set_related_point(self, point: BasePoint, related_point: BasePoint) -> None:
        """设置测点关联（值变化时联动写入）"""
        if not point or not related_point:
            return

        point.related_point = related_point
        point.is_send_signal = True
        point.value_changed.connect(self.on_point_value_changed)
