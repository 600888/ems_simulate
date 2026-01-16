from src.data.dao.point_dao import PointDao
from typing import List


class PointService:
    """点服务类，提供与测点相关的业务逻辑操作"""

    def __init__(self):
        """初始化PointService实例"""
        pass

    @classmethod
    def get_rtu_addr_list(cls, grp_code: str) -> List[int]:
        """获取指定组代码下的RTU地址列表

        Args:
            grp_code: 组代码

        Returns:
            List[int]: RTU地址列表

        Raises:
            Exception: 如果查询过程中发生错误
        """
        return PointDao.get_rtu_addr_list(grp_code)

    @classmethod
    def update_point_limit(
        cls, grp_code: str, code: str, min_value_limit: int, max_value_limit: int
    ) -> bool:
        """更新指定测点的上下限值

        Args:
            grp_code: 组代码
            code: 测点编码
            min_value_limit: 下限值
            max_value_limit: 上限值

        Returns:
            bool: 更新是否成功

        Raises:
            Exception: 如果更新过程中发生错误
        """
        return PointDao.update_point_limit(
            grp_code, code, min_value_limit, max_value_limit
        )
