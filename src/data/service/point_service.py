"""
测点服务模块
提供测点的统一业务入口
"""

from typing import List, Optional

from src.data.dao.point_dao import PointDao
from src.enums.modbus_def import ProtocolType
from src.enums.point_data import Yc, Yx, Yk, Yt, BasePoint

from src.data.service.yc_service import YcService
from src.data.service.yx_service import YxService
from src.data.service.yk_service import YkService
from src.data.service.yt_service import YtService


class PointService:
    """测点服务统一入口"""

    def __init__(self):
        pass

    @classmethod
    def get_all_points(
        cls, channel_id: int, protocol_type: ProtocolType
    ) -> List[BasePoint]:
        """获取通道下所有测点"""
        points: List[BasePoint] = []
        points.extend(YcService.get_list(channel_id, protocol_type))
        points.extend(YxService.get_list(channel_id, protocol_type))
        points.extend(YkService.get_list(channel_id, protocol_type))
        points.extend(YtService.get_list(channel_id, protocol_type))
        return points

    @classmethod
    def get_yc_list(cls, channel_id: int, protocol_type: ProtocolType) -> List[Yc]:
        """获取遥测点列表"""
        return YcService.get_list(channel_id, protocol_type)

    @classmethod
    def get_yx_list(cls, channel_id: int, protocol_type: ProtocolType) -> List[Yx]:
        """获取遥信点列表"""
        return YxService.get_list(channel_id, protocol_type)

    @classmethod
    def get_yk_list(cls, channel_id: int, protocol_type: ProtocolType) -> List[Yk]:
        """获取遥控点列表"""
        return YkService.get_list(channel_id, protocol_type)

    @classmethod
    def get_yt_list(cls, channel_id: int, protocol_type: ProtocolType) -> List[Yt]:
        """获取遥调点列表"""
        return YtService.get_list(channel_id, protocol_type)

    @classmethod
    def get_rtu_addr_list(cls, channel_id: int) -> List[int]:
        """获取通道下的从机地址列表"""
        return PointDao.get_rtu_addr_list(channel_id)

    @classmethod
    def get_point_by_code(cls, code: str) -> Optional[dict]:
        """根据编码获取测点"""
        return PointDao.get_point_by_code(code)

    @classmethod
    def update_point_limit(
        cls, grp_code: str, code: str, min_limit: float, max_limit: float
    ) -> bool:
        """更新测点限值"""
        return PointDao.update_point_metadata(code, {"min_limit": min_limit, "max_limit": max_limit})

    @classmethod
    def update_point_metadata(
        cls, code: str, metadata: dict
    ) -> bool:
        """更新测点元数据"""
        return PointDao.update_point_metadata(code, metadata)
