"""
从机服务层 (SlaveService)
"""

from typing import List, Optional

from src.data.dao.slave_dao import SlaveDao
from src.data.model import SlaveDict
from src.log import log


class SlaveService:
    """从机服务类"""

    @classmethod
    def get_slaves_by_channel(cls, channel_id: int) -> List[SlaveDict]:
        """获取通道下所有从机"""
        return SlaveDao.get_slaves_by_channel(channel_id)

    @classmethod
    def get_slave_ids_by_channel(cls, channel_id: int) -> List[int]:
        """获取通道下所有从机ID列表"""
        return SlaveDao.get_slave_ids_by_channel(channel_id)

    @classmethod
    def slave_exists(cls, channel_id: int, slave_id: int) -> bool:
        """检查从机是否存在"""
        return SlaveDao.slave_exists(channel_id, slave_id)

    @classmethod
    def create_slave(cls, channel_id: int, slave_id: int, name: Optional[str] = None) -> bool:
        """创建从机"""
        if slave_id < 0 or slave_id > 255:
            log.error(f"无效的从机地址: {slave_id}")
            return False
        return SlaveDao.create_slave(channel_id, slave_id, name)

    @classmethod
    def delete_slave(cls, channel_id: int, slave_id: int) -> bool:
        """删除从机"""
        return SlaveDao.delete_slave(channel_id, slave_id)

    @classmethod
    def update_slave_id(cls, channel_id: int, old_slave_id: int, new_slave_id: int) -> bool:
        """更新从机地址"""
        if new_slave_id < 0 or new_slave_id > 255:
            log.error(f"无效的新从机地址: {new_slave_id}")
            return False
        return SlaveDao.update_slave_id(channel_id, old_slave_id, new_slave_id)
