"""
测点管理器模块
统一管理四类测点：遥测、遥信、遥调、遥控
"""

from typing import Dict, List, Optional, Union

from src.enums.points.base_point import BasePoint
from src.enums.point_data import Yc, Yx, Yt, Yk
from src.enums.modbus_def import ProtocolType
from src.data.service.yc_service import YcService
from src.data.service.yx_service import YxService
from src.log import log

class PointManager:
    """测点管理器"""

    def __init__(self):
        # 按从机 ID 分组存储
        self.yc_dict: Dict[int, List[Yc]] = {}
        self.yx_dict: Dict[int, List[Yx]] = {}
        self.yt_dict: Dict[int, List[Yt]] = {}
        self.yk_dict: Dict[int, List[Yk]] = {}

        # 按编码索引
        self.code_map: Dict[str, BasePoint] = {}

        # 按地址索引（用于快速查找）
        self.address_map: Dict[int, Dict[int, BasePoint]] = {}

        # 从机 ID 列表
        self.slave_id_list: List[int] = []

        # 初始化字典
        self._init_dicts()

    def _init_dicts(self) -> None:
        """初始化测点字典"""
        for slave_id in range(256):
            self.yc_dict[slave_id] = []
            self.yx_dict[slave_id] = []
            self.yt_dict[slave_id] = []
            self.yk_dict[slave_id] = []

    def add_point(self, slave_id: int, point: BasePoint) -> None:
        """添加测点
        
        Args:
            slave_id: 从机 ID
            point: 测点对象
        """
        # 添加到对应的字典
        if isinstance(point, Yt):
            self.yt_dict[slave_id].append(point)
        elif isinstance(point, Yk):
            self.yk_dict[slave_id].append(point)
        elif isinstance(point, Yc):
            self.yc_dict[slave_id].append(point)
        elif isinstance(point, Yx):
            self.yx_dict[slave_id].append(point)

        # 更新索引
        if point.code:
            self.code_map[point.code] = point

        # 更新从机 ID 列表
        if slave_id not in self.slave_id_list:
            self.slave_id_list.append(slave_id)

    def get_point_by_code(self, code: str) -> Optional[BasePoint]:
        """根据编码获取测点"""
        return self.code_map.get(code)

    def get_points_by_slave(
        self, slave_id: int
    ) -> tuple[List[Yc], List[Yx], List[Yt], List[Yk]]:
        """获取指定从机的所有测点"""
        return (
            self.yc_dict.get(slave_id, []),
            self.yx_dict.get(slave_id, []),
            self.yt_dict.get(slave_id, []),
            self.yk_dict.get(slave_id, []),
        )

    def get_points_by_type(self, frame_type: int) -> List[BasePoint]:
        """根据帧类型获取所有测点"""
        result: List[BasePoint] = []
        if frame_type == 0:
            for points in self.yc_dict.values():
                result.extend(points)
        elif frame_type == 1:
            for points in self.yx_dict.values():
                result.extend(points)
        elif frame_type == 2:
            for points in self.yk_dict.values():
                result.extend(points)
        elif frame_type == 3:
            for points in self.yt_dict.values():
                result.extend(points)
        return result

    def get_all_points(self) -> List[BasePoint]:
        """获取所有测点"""
        result: List[BasePoint] = []
        for slave_id in self.slave_id_list:
            yc, yx, yt, yk = self.get_points_by_slave(slave_id)
            result.extend(yc)
            result.extend(yx)
            result.extend(yt)
            result.extend(yk)
        return result

    def import_from_db(self, channel_id: int, protocol_type: ProtocolType) -> None:
        """从数据库导入测点
        
        Args:
            channel_id: 通道ID
            protocol_type: 协议类型
        """
        log.debug(f"PointManager: Importing points for channel_id={channel_id}, protocol={protocol_type}")
        
        # 1. 首先加载从机配置 (Slave 表)
        try:
            from src.data.service.slave_service import SlaveService
            slave_ids = SlaveService.get_slave_ids_by_channel(channel_id)
            for slave_id in slave_ids:
                if slave_id not in self.slave_id_list:
                    self.slave_id_list.append(slave_id)
            log.debug(f"PointManager: Loaded {len(slave_ids)} slaves from database: {slave_ids}")
        except Exception as e:
            log.error(f"Failed to load slaves from database: {e}")

        # 2. 导入遥测 (兼容旧数据：如果测点存在但从机不在列表中，会自动添加)
        yc_list = YcService.get_list(channel_id, protocol_type)
        for point in yc_list:
            slave_id = point.rtu_addr
            self.add_point(slave_id, point)

        # 导入遥信
        yx_list = YxService.get_list(channel_id, protocol_type)
        for point in yx_list:
            slave_id = point.rtu_addr
            self.add_point(slave_id, point)
            
        # 导入遥调
        from src.data.service.yt_service import YtService
        yt_list = YtService.get_list(channel_id, protocol_type)
        for point in yt_list:
            slave_id = point.rtu_addr
            self.add_point(slave_id, point)

        # 导入遥控
        from src.data.service.yk_service import YkService
        yk_list = YkService.get_list(channel_id, protocol_type)
        for point in yk_list:
            slave_id = point.rtu_addr
            self.add_point(slave_id, point)
            
        log.debug(f"PointManager: Imported {len(yc_list)} YC, {len(yx_list)} YX, {len(yt_list)} YT, {len(yk_list)} YK points")

    def reset_all_values(self) -> None:
        """重置所有测点值为 0"""
        for point in self.code_map.values():
            point.value = 0

    def get_point_count(self) -> Dict[str, int]:
        """获取各类型测点数量"""
        return {
            "yc": sum(len(points) for points in self.yc_dict.values()),
            "yx": sum(len(points) for points in self.yx_dict.values()),
            "yt": sum(len(points) for points in self.yt_dict.values()),
            "yk": sum(len(points) for points in self.yk_dict.values()),
            "total": len(self.code_map),
        }

    @staticmethod
    def frame_type_dict() -> Dict[int, str]:
        """帧类型名称映射"""
        return {0: "遥测", 1: "遥信", 2: "遥控", 3: "遥调"}
