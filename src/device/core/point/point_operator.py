"""
测点操作器模块
负责测点的增删改查、值读取/写入、元数据编辑等操作。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.data.dao.channel_dao import ChannelDao
from src.data.dao.point_dao import PointDao
from src.data.service.point_service import PointService
from src.data.service.yc_service import YcService
from src.data.service.yk_service import YkService
from src.data.service.yt_service import YtService
from src.data.service.yx_service import YxService
from src.device.protocol.base_handler import ClientHandler
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import BasePoint, SimulateMethod, Yc, Yk, Yt, Yx
from src.enums.points.change_tracker import ChangeSource, track_change

if TYPE_CHECKING:
    from src.device.core.device import Device

# Modbus 客户端协议集合: 这些协议下 Yc/Yx 带有 func_code=01/03 的测点允许客户端写入
_MODBUS_PROTOCOLS = frozenset(
    {
        ProtocolType.ModbusTcpClient,
        ProtocolType.ModbusTcp,
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
            if hasattr(self._device, "serial_port") and self._device.serial_port:
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

    def edit_value(
        self, point_code: str, real_value: float, source: ChangeSource | None = None, detail: str | None = None,
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

        if isinstance(self._handler, ClientHandler) and isinstance(point, (Yc, Yx)):
            # Modbus 协议: func_code=01(读线圈)/03(读保持寄存器) 的 Yc/Yx 允许客户端写入
            if not (self._device.protocol_type in _MODBUS_PROTOCOLS and getattr(point, "func_code", None) in (1, 3)):
                raise ValueError("作为客户端时，只允许对遥控(Yk)和遥调(Yt)类测点进行写入操作")

        # 如果未指定来源，默认使用 MANUAL
        effective_source = source or ChangeSource.MANUAL
        effective_detail = detail or f"手动设置 {point_code}={real_value}"

        with track_change(effective_source, effective_detail):
            if not point.set_real_value(real_value):
                raise ValueError(f"测点 {point_code} 值 {real_value} 超出允许范围")

            if self._handler:
                try:
                    result = self._handler.write_value(point, point.value)
                except Exception as e:
                    raise ValueError(f"测点 {point_code} 写入失败: {e}") from e
                if not result:
                    raise ValueError(f"测点 {point_code} 协议写入失败，请检查配置或物理连接")
                self._log.info(f"测点 {point_code} 写入成功: {real_value}")
                return result
            else:
                raise SystemError(f"测点 {point_code} 协议处理器未配置，无法写入")

    async def edit_value_async(
        self, point_code: str, real_value: float, source: ChangeSource | None = None, detail: str | None = None,
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

        if isinstance(self._handler, ClientHandler) and isinstance(point, (Yc, Yx)):
            # Modbus 协议: func_code=01(读线圈)/03(读保持寄存器) 的 Yc/Yx 允许客户端写入
            if not (self._device.protocol_type in _MODBUS_PROTOCOLS and getattr(point, "func_code", None) in (1, 3)):
                raise SystemError("作为客户端时，只允许对遥控(Yk)和遥调(Yt)类测点进行操作")

        # 如果未指定来源，默认使用 MANUAL
        effective_source = source or ChangeSource.MANUAL
        effective_detail = detail or f"手动设置 {point_code}={real_value}"

        with track_change(effective_source, effective_detail):
            if not point.set_real_value(real_value):
                self._log.error(f"测点 {point_code} 值 {real_value} 超出允许范围")
                raise ValueError(f"测点 {point_code} 值 {real_value} 超出允许范围")

            if self._handler:
                try:
                    if hasattr(self._handler, "write_value_async"):
                        result = await self._handler.write_value_async(point, point.value)
                    else:
                        result = self._handler.write_value(point, point.value)
                except Exception as e:
                    self._log.error(f"测点 {point_code} 写入失败: {e}")
                    raise ValueError(f"测点 {point_code} 写入失败: {e}") from e
                if not result:
                    self._log.error(f"测点 {point_code} 协议写入失败，请检查配置或物理连接")
                    raise ValueError(f"测点 {point_code} 协议写入失败，请检查配置或物理连接")
                self._log.info(f"测点 {point_code} 写入成功: {real_value}")
                return result
            else:
                self._log.error(f"测点 {point_code} 协议处理器未配置，无法写入")
                raise ValueError(f"测点 {point_code} 协议处理器未配置，无法写入")

    def read_single_point(self, point_code: str, slave_id: int | None = None) -> float | None:
        """读取单个测点的值

        Args:
            point_code: 测点编码
            slave_id: 从机 ID，不同从站编码相同时用于精确定位测点

        Returns:
            Optional[float]: 读取成功返回值，失败返回None
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
                return (
                    float(point.value)
                    if getattr(point, "bit", None) is not None
                    else (point.real_value if hasattr(point, "real_value") else float(value))
                )
            else:
                point.is_valid = False
                self._log.info(f"读取测点 {point_code} 失败: {value}")
        except Exception as e:
            self._log.error(f"读取测点 {point_code} 失败: {e}")
            point.is_valid = False
            raise ValueError(f"读取测点 {point_code} 失败: {e}") from e

    async def read_single_point_async(self, point_code: str, slave_id: int | None = None) -> float | None:
        """异步读取单个测点的值

        Args:
            point_code: 测点编码
            slave_id: 从机 ID，不同从站编码相同时用于精确定位测点

        Returns:
            Optional[float]: 读取成功返回值，失败返回None
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
                return (
                    float(point.value)
                    if getattr(point, "bit", None) is not None
                    else (point.real_value if hasattr(point, "real_value") else float(value))
                )
            else:
                point.is_valid = False
                self._log.info(f"异步读取测点 {point_code} 失败: {value}")
        except Exception as e:
            self._log.error(f"异步读取测点 {point_code} 失败: {e}")
            point.is_valid = False

        return None

    async def read_metadata_async(self, point_code: str, slave_id: int | None = None) -> dict:
        """异步读取测点的品质(q)与时标(t)元数据"""
        if not self._handler:
            return {"quality": {}, "timestamp": {}}

        if not hasattr(self._handler, "read_metadata_async"):
            self._log.debug(f"协议处理器不支持元数据读取: {point_code}")
            return {"quality": {}, "timestamp": {}}

        # point_code 可能是完整 DA 地址或 DO 引用，直接传给客户端
        from src.enums.points.base_point import BasePoint
        temp_point = BasePoint()
        temp_point.address = point_code
        temp_point.fc = ""
        return await self._handler.read_metadata_async(temp_point)

    # ===== 测点元数据编辑 =====

    def edit_metadata(self, point_code: str, metadata: dict) -> bool:
        """编辑测点元数据"""
        point = self._pm.get_point_by_code(point_code)
        if not point:
            raise ValueError(f"未找到测点: {point_code}")

        # 记录是否需要重新同步值到协议处理器
        need_resync = False
        current_real_value = getattr(point, "real_value", None)

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

        if isinstance(point, (Yk, Yx)) and "bit" in metadata:
            old_bit = getattr(point, "bit", None)
            val = metadata["bit"]
            new_bit = int(val) if val is not None and str(val) != "" else None
            point.bit = new_bit
            if old_bit != new_bit:
                need_resync = True

        if isinstance(point, (Yc, Yt)):
            if "mul_coe" in metadata and str(metadata["mul_coe"]) != "":
                old_mul_coe = point.mul_coe
                point.mul_coe = float(metadata["mul_coe"])
                if old_mul_coe != float(metadata["mul_coe"]):
                    need_resync = True
            if "add_coe" in metadata and str(metadata["add_coe"]) != "":
                old_add_coe = point.add_coe
                point.add_coe = float(metadata["add_coe"])
                if old_add_coe != float(metadata["add_coe"]):
                    need_resync = True

        # 处理 IEC104 类型标识修改
        if "iec_type_id" in metadata:
            old_iec_type_id = getattr(point, "iec_type_id", None)
            new_iec_type_id = metadata["iec_type_id"] if metadata["iec_type_id"] else None
            if old_iec_type_id != new_iec_type_id:
                point.iec_type_id = new_iec_type_id
                need_resync = True  # IEC104 类型变更需要重新同步

        # 处理 IEC104 品质描述符修改
        if "iec_quality" in metadata:
            new_quality = metadata["iec_quality"]
            if new_quality is not None:
                point.iec_quality_value = int(new_quality)
                need_resync = True  # 品质变更需要重新同步

        # 处理 code 修改
        if "code" in metadata and metadata["code"] and metadata["code"] != point_code:
            new_code = metadata["code"]
            slave_id = point.rtu_addr
            # 更新 PointManager 的索引
            self._pm.rename_point_in_index(point_code, new_code, slave_id)
            point.code = new_code

        # 3. 如果配置发生变更，重新将真实值写入协议处理器
        if need_resync and self._handler:
            # IEC104 协议下 iec_type_id 变更需要重新同步（影响编码方式）
            protocol_type = self._device.protocol_type
            if protocol_type in [ProtocolType.Iec104Server, ProtocolType.Iec104Client]:
                try:
                    if isinstance(point, (Yc, Yt)) and current_real_value is not None:
                        if point.set_real_value(current_real_value):
                            result = self._handler.write_value(point, point.value)
                            if result:
                                self._log.info(f"测点 {point.code} 元数据更新后已重新同步值到 IEC104 协议处理器")
                            else:
                                self._log.warning(f"重新同步测点 {point.code} 值失败")
                    elif isinstance(point, (Yx, Yk)):
                        result = self._handler.write_value(point, point.value)
                        if result:
                            self._log.info(f"测点 {point.code} 元数据更新后已重新同步值到 IEC104 协议处理器")
                        else:
                            self._log.warning(f"重新同步测点 {point.code} 值失败")
                except Exception as e:
                    self._log.warning(f"重新同步测点 {point.code} 值失败: {e}")
            elif current_real_value is not None and isinstance(point, (Yk, Yt)):
                try:
                    # 使用新的配置重新计算并写入
                    if point.set_real_value(current_real_value):
                        result = self._handler.write_value(point, point.value)
                        if result:
                            self._log.info(f"测点 {point.code} 元数据更新后已重新同步值到协议处理器")
                        else:
                            self._log.warning(f"重新同步测点 {point.code} 值失败: 编辑完配置同步失败")
                except Exception as e:
                    self._log.warning(f"重新同步测点 {point.code} 值失败: {e}")

        # 4. 更新数据库
        try:
            channel_id = self._get_channel_id()
            return PointService.update_point_metadata(point_code, metadata, channel_id)
        except Exception as e:
            self._log.error(f"更新测点元数据失败: {e}")
            return False

    def edit_limit(self, point_code: str, min_value_limit: int, max_value_limit: int) -> bool:
        """编辑测点限值"""
        point = self._pm.get_point_by_code(point_code)
        if not point or not isinstance(point, (Yc, Yt)):
            return False

        point.max_value_limit = max_value_limit
        point.min_value_limit = min_value_limit
        try:
            channel_id = self._get_channel_id()
            return PointService.update_point_limit(
                self._device.name, point_code, min_value_limit, max_value_limit, channel_id
            )
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
            self._device.simulation_controller.add_point(point, SimulateMethod.Random, 1)
            self._device.simulation_controller.set_point_status(point, True)

            # 5. 添加到协议处理器
            if self._handler:
                # IEC104 协议需要重新初始化
                if protocol_type in [ProtocolType.Iec104Server, ProtocolType.Iec104Client]:
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
                point: BasePoint
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
                self._pm.add_point(slave_id, point)

                # 4. 添加到模拟控制器
                self._device.simulation_controller.add_point(point, SimulateMethod.Random, 1)
                self._device.simulation_controller.set_point_status(point, True)

                memory_points.append(point)

            # 5. 添加到协议处理器
            if self._handler:
                if protocol_type in [ProtocolType.Iec104Server, ProtocolType.Iec104Client]:
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
            if self._device.protocol_type in [ProtocolType.Iec104Server, ProtocolType.Iec104Client]:
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
