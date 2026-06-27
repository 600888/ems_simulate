"""
设备服务模块
提供设备的业务逻辑
"""

from src.data.dao.device_dao import DeviceDao
from src.data.log import log
from src.data.model.device import DeviceDict


class DeviceService:
    """设备服务类"""

    def __init__(self):
        pass

    @classmethod
    def get_all_devices(cls) -> list[DeviceDict]:
        """获取所有启用的设备"""
        try:
            return DeviceDao.get_all_devices()
        except Exception as e:
            log.error(f"获取设备列表失败: {e}")
            return []

    @classmethod
    def get_device_by_code(cls, code: str) -> DeviceDict | None:
        """根据编码获取设备"""
        try:
            return DeviceDao.get_device_by_code(code)
        except Exception as e:
            log.error(f"获取设备失败: {e}")
            return None

    @classmethod
    def get_device_by_id(cls, device_id: int) -> DeviceDict | None:
        """根据ID获取设备"""
        try:
            return DeviceDao.get_device_by_id(device_id)
        except Exception as e:
            log.error(f"获取设备失败: {e}")
            return None

    @classmethod
    def create_device(cls, code: str, name: str, device_type: int = 0, group_id: int | None = None) -> int:
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

    # ==== IEC 61850 ICD 路径管理 ====

    @classmethod
    def set_icd_path(cls, device_id: int, icd_path: str, file_hash: str = "") -> bool:
        """设置设备的 ICD 文件路径"""
        try:
            return DeviceDao.set_device_icd_path(device_id, icd_path, file_hash)
        except Exception as e:
            log.error(f"设置设备 ICD 路径失败: {e}")
            return False

    @classmethod
    def get_icd_path(cls, device_id: int) -> str | None:
        """获取设备的 ICD 文件路径"""
        try:
            return DeviceDao.get_device_icd_path(device_id)
        except Exception as e:
            log.error(f"获取设备 ICD 路径失败: {e}")
            return None

    @classmethod
    def get_devices_by_icd_path(cls, icd_path: str) -> list[DeviceDict]:
        """根据 ICD 文件路径查找关联的设备列表"""
        try:
            return DeviceDao.get_devices_by_icd_path(icd_path)
        except Exception as e:
            log.error(f"通过 ICD 路径查找设备失败: {e}")
            return []
