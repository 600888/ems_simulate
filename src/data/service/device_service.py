"""
设备服务模块
提供设备的业务逻辑
"""

from typing import List, Optional
from src.data.dao.device_dao import DeviceDao
from src.data.model.device import DeviceDict
from src.data.log import log


class DeviceService:
    """设备服务类"""

    def __init__(self):
        pass

    @classmethod
    def get_all_devices(cls) -> List[DeviceDict]:
        """获取所有启用的设备"""
        try:
            return DeviceDao.get_all_devices()
        except Exception as e:
            log.error(f"获取设备列表失败: {e}")
            return []

    @classmethod
    def get_device_by_code(cls, code: str) -> Optional[DeviceDict]:
        """根据编码获取设备"""
        try:
            return DeviceDao.get_device_by_code(code)
        except Exception as e:
            log.error(f"获取设备失败: {e}")
            return None

    @classmethod
    def get_device_by_id(cls, device_id: int) -> Optional[DeviceDict]:
        """根据ID获取设备"""
        try:
            return DeviceDao.get_device_by_id(device_id)
        except Exception as e:
            log.error(f"获取设备失败: {e}")
            return None

    @classmethod
    def create_device(cls, code: str, name: str, device_type: int = 0, group_id: Optional[int] = None) -> int:
        """创建设备"""
        try:
            return DeviceDao.create_device(code, name, device_type, group_id)
        except Exception as e:
            log.error(f"创建设备失败: {e}")
            return -1

    @classmethod
    def update_device(cls, device_id: int, **kwargs) -> bool:
        """更新设备"""
        try:
            return DeviceDao.update_device(device_id, **kwargs)
        except Exception as e:
            log.error(f"更新设备失败: {e}")
            return False

    @classmethod
    def delete_device(cls, device_id: int) -> bool:
        """删除设备"""
        try:
            return DeviceDao.delete_device(device_id)
        except Exception as e:
            log.error(f"删除设备失败: {e}")
            return False
