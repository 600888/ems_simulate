"""
从机管理器模块
负责从机的动态增删改操作，包括内存状态更新、数据库持久化和协议同步。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from src.enums.point_data import Yc, Yx, Yt, Yk
from src.enums.modbus_def import ProtocolType

if TYPE_CHECKING:
    from src.device.core.device import Device


class SlaveManager:
    """从机管理器
    
    管理设备下属从机的增删改操作，协调内存、数据库和协议三层的一致性。
    """

    def __init__(self, device: "Device") -> None:
        self._device = device

    @property
    def _pm(self):
        """获取测点管理器"""
        return self._device.point_manager

    @property
    def _log(self):
        """获取日志器"""
        return self._device.log

    def add_slave(self, slave_id: int) -> bool:
        """动态添加从机
        
        Args:
            slave_id: 从机地址 (1-255)
            
        Returns:
            是否添加成功
        """
        try:
            from src.data.service.slave_service import SlaveService

            if slave_id < 0 or slave_id > 255:
                self._log.error(f"无效的从机地址: {slave_id}")
                return False

            if slave_id in self._pm.slave_id_list:
                self._log.warning(f"从机 {slave_id} 已存在")
                return False

            # 1. 持久化到数据库
            if not SlaveService.create_slave(self._device.device_id, slave_id):
                self._log.error(f"保存从机到数据库失败: {slave_id}")
                return False

            # 2. 添加到内存中的从机列表
            self._pm.slave_id_list.append(slave_id)
            self._pm.slave_id_list.sort()

            # 3. 同步更新底层协议服务器 (Modbus)
            server = self._device.server
            if server and hasattr(server, "add_slave"):
                server.add_slave(slave_id)

            self._log.info(f"动态添加从机成功: {slave_id}")
            return True

        except Exception as e:
            self._log.error(f"动态添加从机失败: {e}")
            return False

    def delete_slave(self, slave_id: int) -> bool:
        """动态删除从机
        
        Args:
            slave_id: 从机地址
            
        Returns:
            是否删除成功
        """
        try:
            from src.data.service.slave_service import SlaveService

            if slave_id not in self._pm.slave_id_list:
                self._log.warning(f"从机 {slave_id} 不存在")
                return False

            # 1. 从数据库删除从机记录
            if not SlaveService.delete_slave(self._device.device_id, slave_id):
                self._log.error(f"从数据库删除从机失败: {slave_id}")
                return False

            # 2. 清空该从机的所有测点
            self.clear_points_by_slave(slave_id)

            # 3. 从列表中移除
            self._pm.slave_id_list.remove(slave_id)

            # 4. 同步更新底层协议服务器 (Modbus)
            server = self._device.server
            if server and hasattr(server, "remove_slave"):
                server.remove_slave(slave_id)

            # 5. 如果是 IEC104，需要重新初始化
            if self._device.protocol_type in [
                ProtocolType.Iec104Server, ProtocolType.Iec104Client
            ]:
                self._device._reinit_protocol_for_iec104()

            self._log.info(f"动态删除从机成功: {slave_id}")
            return True

        except Exception as e:
            import traceback
            traceback.print_exc()
            self._log.error(f"动态删除从机失败: {e}")
            return False

    def edit_slave(self, old_slave_id: int, new_slave_id: int) -> bool:
        """动态编辑从机（修改从机地址）
        
        Args:
            old_slave_id: 旧从机地址
            new_slave_id: 新从机地址
            
        Returns:
            是否编辑成功
        """
        try:
            from src.data.service.slave_service import SlaveService

            if old_slave_id not in self._pm.slave_id_list:
                self._log.warning(f"从机 {old_slave_id} 不存在")
                return False

            if new_slave_id < 0 or new_slave_id > 255:
                self._log.error(f"无效的新从机地址: {new_slave_id}")
                return False

            if old_slave_id == new_slave_id:
                return True

            if new_slave_id in self._pm.slave_id_list:
                self._log.warning(f"从机 {new_slave_id} 已存在，无法修改为该地址")
                return False

            device_id = self._device.device_id

            # 1. 更新数据库中的从机地址
            if not SlaveService.update_slave_id(device_id, old_slave_id, new_slave_id):
                self._log.error(
                    f"更新从机地址到数据库失败: {old_slave_id} -> {new_slave_id}"
                )
                return False

            # 2. 迁移测点字典
            for dict_attr in ['yc_dict', 'yx_dict', 'yk_dict', 'yt_dict']:
                d = getattr(self._pm, dict_attr)
                if old_slave_id in d:
                    d[new_slave_id] = d.pop(old_slave_id)
                else:
                    d[new_slave_id] = []

            # 3. 更新内存中所有测点对象的 slave_id
            points_tuple = self._pm.get_points_by_slave(new_slave_id)
            for point_list in points_tuple:
                for point in point_list:
                    point.slave_id = new_slave_id
                    point.rtu_addr = new_slave_id

            # 4. 持久化到数据库 (测点表中的 rtu_addr)
            from src.data.dao.point_dao import PointDao
            PointDao.update_slave_id(device_id, old_slave_id, new_slave_id)

            # 5. 更新 slave_id_list
            if old_slave_id in self._pm.slave_id_list:
                self._pm.slave_id_list.remove(old_slave_id)

            if new_slave_id not in self._pm.slave_id_list:
                self._pm.slave_id_list.append(new_slave_id)
                self._pm.slave_id_list.sort()

            # 6. 同步更新底层协议服务器 (Modbus)
            server = self._device.server
            if server and hasattr(server, "add_slave") and hasattr(server, "remove_slave"):
                server.add_slave(new_slave_id)
                server.remove_slave(old_slave_id)

            # 7. 协议重置 (IEC104)
            if self._device.protocol_type in [
                ProtocolType.Iec104Server, ProtocolType.Iec104Client
            ]:
                self._device._reinit_protocol_for_iec104()

            self._log.info(f"动态编辑从机成功: {old_slave_id} -> {new_slave_id}")
            return True

        except Exception as e:
            self._log.error(f"动态编辑从机失败: {e}")
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
            point_codes: List[str] = []

            for dict_attr in ['yc_dict', 'yx_dict', 'yk_dict', 'yt_dict']:
                d = getattr(self._pm, dict_attr)
                if slave_id in d:
                    for point in d[slave_id]:
                        point_codes.append(point.code)

            # 批量删除
            for code in point_codes:
                # 从数据库删除
                if PointDao.delete_point_by_code(code):
                    deleted_count += 1
                # 从 code_map 移除
                if code in self._pm.code_map:
                    del self._pm.code_map[code]

            # 清空内存中的测点列表
            for dict_attr in ['yc_dict', 'yx_dict', 'yk_dict', 'yt_dict']:
                d = getattr(self._pm, dict_attr)
                if slave_id in d:
                    d[slave_id] = []

            # IEC104 协议需要重新初始化
            if self._device.protocol_type in [
                ProtocolType.Iec104Server, ProtocolType.Iec104Client
            ]:
                self._device._reinit_protocol_for_iec104()

            self._log.info(
                f"清空从机 {slave_id} 的测点成功，共删除 {deleted_count} 个测点"
            )

            return deleted_count

        except Exception as e:
            self._log.error(f"清空从机测点失败: {e}")
            return 0
