"""
测点管理器模块
统一管理四类测点：遥测、遥信、遥调、遥控
"""

from src.data.service.yc_service import YcService
from src.data.service.yx_service import YxService
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yc, Yk, Yt, Yx
from src.enums.points.base_point import BasePoint
from src.log import log


class PointManager:
    """测点管理器"""

    def __init__(self):
        # 按从机 ID 分组存储
        self.yc_dict: dict[int, list[Yc]] = {}
        self.yx_dict: dict[int, list[Yx]] = {}
        self.yt_dict: dict[int, list[Yt]] = {}
        self.yk_dict: dict[int, list[Yk]] = {}

        # 按编码索引（单从站场景，编码相同的后添加的覆盖先添加的）
        self.code_map: dict[str, BasePoint] = {}

        # 按 (从站, 编码) 索引，支持不同从站使用相同编码
        # slave_code_index[slave_id][code] -> point
        self.slave_code_index: dict[int, dict[str, BasePoint]] = {}

        # 按地址索引（用于快速查找）
        self.address_map: dict[int, dict[int, BasePoint]] = {}

        # 从机 ID 列表
        self.slave_id_list: list[int] = []

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

        # 更新索引 - 使用复合键避免不同从站同编码覆盖
        if point.code:
            composite_key = f"{slave_id}:{point.code}"
            self.code_map[composite_key] = point
            # 同时维护 slave_code_index（支持不同从站使用相同编码）
            if slave_id not in self.slave_code_index:
                self.slave_code_index[slave_id] = {}
            self.slave_code_index[slave_id][point.code] = point

        # 更新从机 ID 列表
        if slave_id not in self.slave_id_list:
            self.slave_id_list.append(slave_id)

    def get_point_by_code(self, code: str, slave_id: int | None = None) -> BasePoint | None:
        """根据编码获取测点

        Args:
            code: 测点编码
            slave_id: 从机 ID，为 None 时遍历所有从站查找第一个匹配项
                      指定从机 ID 时精确查找该从机下的测点

        Returns:
            测点对象，未找到返回 None
        """
        if slave_id is not None:
            # 精确查找：从 slave_code_index 定位
            slave_points = self.slave_code_index.get(slave_id)
            if slave_points:
                return slave_points.get(code)
            # 兼容旧数据：composite_key 回退
            return self.code_map.get(f"{slave_id}:{code}")
        # 无 slave_id：先尝试 code_map 中查找（原 simple key 兼容）
        direct = self.code_map.get(code)
        if direct:
            return direct
        # 再遍历 slave_code_index
        for slave_points in self.slave_code_index.values():
            if code in slave_points:
                return slave_points[code]
        return None

    def get_points_by_slave(self, slave_id: int) -> tuple[list[Yc], list[Yx], list[Yt], list[Yk]]:
        """获取指定从机的所有测点"""
        return (
            self.yc_dict.get(slave_id, []),
            self.yx_dict.get(slave_id, []),
            self.yt_dict.get(slave_id, []),
            self.yk_dict.get(slave_id, []),
        )

    def get_points_by_type(self, frame_type: int) -> list[BasePoint]:
        """根据帧类型获取所有测点"""
        result: list[BasePoint] = []
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

    def find_point_by_address_and_type(self, address: int, frame_type: int) -> BasePoint | None:
        """根据地址和帧类型查找测点

        Args:
            address: 测点地址
            frame_type: 帧类型 (0=遥测, 1=遥信, 2=遥控, 3=遥调)

        Returns:
            匹配的测点对象，未找到返回 None
        """
        points = self.get_points_by_type(frame_type)
        for point in points:
            if point.address == address:
                return point
        return None

    def get_all_points(self) -> list[BasePoint]:
        """获取所有测点"""
        result: list[BasePoint] = []
        for slave_id in self.slave_id_list:
            yc, yx, yt, yk = self.get_points_by_slave(slave_id)
            result.extend(yc)
            result.extend(yx)
            result.extend(yt)
            result.extend(yk)
        return result

    def add_point_to_index(self, slave_id: int, point: BasePoint) -> None:
        """将测点加入索引（code_map 和 slave_code_index）

        供外部代码（如 data_importer）使用，避免直接操作 code_map 导致索引不一致。
        """
        if not point.code:
            return
        composite_key = f"{slave_id}:{point.code}"
        self.code_map[composite_key] = point
        if slave_id not in self.slave_code_index:
            self.slave_code_index[slave_id] = {}
        self.slave_code_index[slave_id][point.code] = point

    def remove_point_from_index(self, point_code: str, slave_id: int | None = None) -> None:
        """从索引中移除测点

        同时清理 code_map 和 slave_code_index。
        slave_id 为 None 时尝试清理所有可能的 key。
        """
        # 清理 code_map
        if slave_id is not None:
            composite_key = f"{slave_id}:{point_code}"
            if composite_key in self.code_map:
                del self.code_map[composite_key]
        if point_code in self.code_map:
            del self.code_map[point_code]
        for sid, slave_points in list(self.slave_code_index.items()):
            if slave_id is not None and sid != slave_id:
                continue
            if point_code in slave_points:
                del slave_points[point_code]
                if not slave_points:
                    del self.slave_code_index[sid]

    def rename_point_in_index(self, old_code: str, new_code: str, slave_id: int) -> None:
        """在索引中重命名测点编码"""
        # 更新 code_map
        old_composite = f"{slave_id}:{old_code}"
        if old_composite in self.code_map:
            point = self.code_map.pop(old_composite)
            new_composite = f"{slave_id}:{new_code}"
            self.code_map[new_composite] = point
        # 更新 slave_code_index
        if slave_id in self.slave_code_index and old_code in self.slave_code_index[slave_id]:
            point = self.slave_code_index[slave_id].pop(old_code)
            self.slave_code_index[slave_id][new_code] = point

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

        log.debug(
            f"PointManager: Imported {len(yc_list)} YC, {len(yx_list)} YX, {len(yt_list)} YT, {len(yk_list)} YK points"
        )

    def reset_all_values(self) -> None:
        """重置所有测点值为 0"""
        for point in self.code_map.values():
            point.value = 0
        # 确保 slave_code_index 中的点也被重置（可能超出 code_map 覆盖范围）
        for slave_points in self.slave_code_index.values():
            for point in slave_points.values():
                if point.code not in self.code_map:
                    point.value = 0

    def get_point_count(self) -> dict[str, int]:
        """获取各类型测点数量"""
        # 使用 slave_code_index 去重计算总点数
        total_points = set()
        for slave_points in self.slave_code_index.values():
            total_points.update(slave_points.values())
        return {
            "yc": sum(len(points) for points in self.yc_dict.values()),
            "yx": sum(len(points) for points in self.yx_dict.values()),
            "yt": sum(len(points) for points in self.yt_dict.values()),
            "yk": sum(len(points) for points in self.yk_dict.values()),
            "total": len(total_points),
        }

    @staticmethod
    def frame_type_dict() -> dict[int, str]:
        """帧类型名称映射"""
        return {0: "遥测", 1: "遥信", 2: "遥控", 3: "遥调"}
