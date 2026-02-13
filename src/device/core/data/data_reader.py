"""
数据读取器模块
负责从协议处理器读取测点数据，支持同步/异步/批量读取模式。
协议无关设计，支持 Modbus、IEC104、DLT645 等协议。
"""

from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Dict, Optional, Tuple, Union

from src.enums.point_data import Yc, Yx, BasePoint
from src.enums.modbus_register import Decode

if TYPE_CHECKING:
    from src.device.core.device import Device


@dataclass
class AddressGroup:
    """地址分组 - 用于批量读取优化
    
    将连续地址的测点分组，以便一次性读取多个数据点。
    
    Attributes:
        start_address: 起始地址
        register_count: 需要读取的数据点数量
        points: 该组包含的测点列表
    """
    start_address: int
    register_count: int
    points: List[BasePoint] = field(default_factory=list)


class DataReader:
    """数据读取器
    
    负责从协议处理器读取测点数据，将协议层的原始数据转换为应用层的测点值。
    支持同步读取、异步逐点读取、异步批量读取三种模式。
    """

    def __init__(self, device: "Device") -> None:
        self._device = device

    @property
    def _handler(self):
        """获取协议处理器（始终跟踪 device 的最新实例）"""
        return self._device.protocol_handler

    @property
    def _log(self):
        """获取日志器"""
        return self._device.log

    def get_slave_values(
        self, yc_list: List[Yc], yx_list: List[Yx]
    ) -> None:
        """同步读取从机的测点值
        
        Args:
            yc_list: 遥测列表
            yx_list: 遥信列表
        """
        if not self._handler:
            return

        for point in yc_list + yx_list:
            try:
                value = self._handler.read_value(point)
                if value is not None:
                    point.value = value
                    point.is_valid = True
                else:
                    point.is_valid = False
            except (ConnectionError, Exception):
                # 连接失败时静默处理，不中断线程
                point.is_valid = False

    async def get_slave_values_async(
        self, yc_list: List[Yc], yx_list: List[Yx], interval_ms: int = 0
    ) -> Tuple[int, int]:
        """异步读取从机的测点值（支持批量读取优化）
        
        Args:
            yc_list: 遥测列表
            yx_list: 遥信列表
            interval_ms: 每次批量读取请求之间的间隔(毫秒)
            
        Returns:
            Tuple[int, int]: (成功点数, 失败点数)
        
        对于 Modbus 客户端，会将连续地址的测点合并为一次批量读取请求。
        对于其他协议或服务端，回退到逐点读取模式。
        """
        if not self._handler:
            if self._device._logger:
                self._device._logger.warning(
                    "get_slave_values_async: No protocol handler"
                )
            return 0, 0

        all_points = yc_list + yx_list
        if not all_points:
            return 0, 0

        # 检查是否是 Modbus 客户端，支持批量读取
        from src.device.protocol.modbus_handler import ModbusClientHandler
        is_modbus_client = isinstance(self._handler, ModbusClientHandler)

        if is_modbus_client and hasattr(self._handler, 'read_registers_batch_async'):
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
                if hasattr(self._handler, 'read_value_async'):
                    value = await self._handler.read_value_async(point)
                else:
                    value = self._handler.read_value(point)

                if value is not None:
                    point.value = value
                    point.is_valid = True
                    success_count += 1
                else:
                    point.is_valid = False
                    fail_count += 1
            except (ConnectionError, Exception) as e:
                self._log.error(f"Error reading point {point.code}: {e}")
                point.is_valid = False
                fail_count += 1
        return success_count, fail_count

    async def _batch_read_async(
        self, points: List[BasePoint], interval_ms: int = 0
    ) -> Tuple[int, int]:
        """批量读取模式（优化方案）
        
        将连续地址的测点分组，一次性读取多个数据点，然后解码映射。
        
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

                    # 2. 批量读取
                    registers = await self._handler.read_registers_batch_async(
                        func_code, slave_id, group.start_address, group.register_count
                    )

                    if registers:
                        # 3. 解码并映射到测点
                        self._decode_batch_registers(
                            registers, group.points, group.start_address
                        )
                        success_count += len(group.points)
                    else:
                        # 读取失败，标记所有测点无效
                        for point in group.points:
                            point.is_valid = False
                        fail_count += len(group.points)

                except Exception as e:
                    self._log.error(
                        f"Batch read error for slave={slave_id}, func={func_code}: {e}"
                    )
                    for point in group.points:
                        point.is_valid = False
                    fail_count += len(group.points)

        return success_count, fail_count

    def _group_points_by_address(
        self,
        points: List[BasePoint],
        max_gap: int = 0,
        max_count: int = 120,
    ) -> Dict[Tuple[int, int], List[AddressGroup]]:
        """将测点按 (slave_id, func_code) 分组，并找出连续的地址段
        
        Args:
            points: 测点列表
            max_gap: 允许的最大地址间隙（默认0，即必须严格连续）
            max_count: 每次批量读取的最大数据点数量（默认120）
            
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
                        points=[point],
                    )
                else:
                    current_end = (
                        current_group.start_address + current_group.register_count
                    )

                    # 计算合并后的新结束地址和数量
                    new_end = max(current_end, point_end_addr)
                    new_count = new_end - current_group.start_address

                    # 检查是否连续或在允许的间隙内，且总数量不超过限制
                    if (
                        point.address <= current_end + max_gap
                        and new_count <= max_count
                    ):
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
                            points=[point],
                        )

            # 保存最后一个分组
            if current_group:
                address_groups.append(current_group)

            result[key] = address_groups

            # 日志记录优化效果
            if len(point_list) > 1:
                total_points = len(point_list)
                total_groups = len(address_groups)
                self._log.debug(
                    f"Batch optimization: {total_points} points -> {total_groups} requests "
                    f"(slave={key[0]}, func={key[1]})"
                )

        return result

    def _decode_batch_registers(
        self,
        registers: List[int],
        points: List[BasePoint],
        start_address: int,
    ) -> None:
        """将批量读取的数据解码并映射到测点
        
        Args:
            registers: 读取到的原始数据列表
            points: 需要解码的测点列表
            start_address: 数据起始地址
        """
        for point in points:
            try:
                # 计算该测点在数据数组中的偏移
                offset = point.address - start_address
                decode_info = Decode.get_info(point.decode)
                reg_count = decode_info.register_cnt

                # 检查偏移是否有效
                if offset < 0 or offset + reg_count > len(registers):
                    point.is_valid = False
                    if self._device._logger:
                        self._device._logger.warning(
                            f"Invalid offset for point {point.code}: offset={offset}, "
                            f"reg_count={reg_count}, total_regs={len(registers)}"
                        )
                    continue

                # 提取该测点对应的数据
                point_registers = registers[offset : offset + reg_count]

                # 解码
                value = self._decode_registers(point_registers, decode_info)

                if value is not None:
                    point.value = value
                    point.is_valid = True
                else:
                    point.is_valid = False

            except Exception as e:
                self._log.error(f"Error decoding point {point.code}: {e}")
                point.is_valid = False

    def _decode_registers(
        self, registers: List[int], decode_info
    ) -> Optional[Union[int, float]]:
        """将原始数据解码为实际值
        
        Args:
            registers: 原始数据列表
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
                    *registers[:4],
                )
            elif reg_count == 2:  # 32位
                packed = struct.pack(
                    ">HH" if decode_info.is_big_endian else "<HH",
                    *registers[:2],
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
            self._log.error(f"Decode error: {e}, registers={registers}")
            return None

    def sync_iec104_client_values(self, slave_id: int) -> None:
        """同步 IEC104 客户端从服务端接收的值到内部测点
        
        当服务端主动上报数据时，c104.Point 对象的 .value 会自动更新，
        此方法将这些值同步到应用内部的测点对象。
        """
        try:
            from src.device.protocol.iec104_handler import IEC104ClientHandler

            if not isinstance(self._handler, IEC104ClientHandler):
                return

            if not self._handler._is_running:
                return

            client = self._handler._client
            if not client or not client.station:
                return

            # 获取该从机下的所有测点 (yc, yx, yt, yk)
            yc_list, yx_list, yt_list, yk_list = self._device.point_manager.get_points_by_slave(
                slave_id
            )
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
                                raw_val = int(
                                    (float(real_val) - point.add_coe) / point.mul_coe
                                )
                                point.value = raw_val
                            except (ZeroDivisionError, TypeError):
                                pass
                        else:
                            point.value = real_val
                except Exception as e:
                    self._log.debug(f"同步测点 {point.code} 失败: {e}")
        except Exception as e:
            self._log.error(f"IEC104 客户端数据同步失败: {e}")
