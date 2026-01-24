"""
设备组服务模块
提供设备组的业务逻辑，支持多层嵌套和批量设备操作
"""

from typing import List, Optional
from src.data.dao.device_group_dao import DeviceGroupDao
from src.data.model.device_group import DeviceGroupDict
from src.data.log import log


class DeviceGroupService:
    """设备组服务类"""

    def __init__(self):
        pass

    @classmethod
    def get_all_groups(cls) -> List[DeviceGroupDict]:
        """获取所有设备组"""
        try:
            return DeviceGroupDao.get_all_groups()
        except Exception as e:
            log.error(f"获取设备组列表失败: {e}")
            return []

    @classmethod
    def get_root_groups(cls) -> List[DeviceGroupDict]:
        """获取顶级设备组"""
        try:
            return DeviceGroupDao.get_root_groups()
        except Exception as e:
            log.error(f"获取顶级设备组失败: {e}")
            return []

    @classmethod
    def get_children_groups(cls, parent_id: int) -> List[DeviceGroupDict]:
        """获取子设备组"""
        try:
            return DeviceGroupDao.get_children_groups(parent_id)
        except Exception as e:
            log.error(f"获取子设备组失败: {e}")
            return []

    @classmethod
    def get_group_tree(cls) -> dict:
        """获取完整设备组树形结构（包含未分组设备）
        
        Returns:
            {
                "groups": [...],  # 设备组树
                "ungrouped": [...],  # 未分组设备
            }
        """
        try:
            groups = DeviceGroupDao.get_group_tree()
            ungrouped = DeviceGroupDao.get_ungrouped_devices()
            return {
                "groups": groups,
                "ungrouped": ungrouped,
            }
        except Exception as e:
            log.error(f"获取设备组树失败: {e}")
            return {"groups": [], "ungrouped": []}

    @classmethod
    def get_group_by_id(cls, group_id: int) -> Optional[DeviceGroupDict]:
        """根据ID获取设备组"""
        try:
            return DeviceGroupDao.get_group_by_id(group_id)
        except Exception as e:
            log.error(f"获取设备组失败: {e}")
            return None

    @classmethod
    def get_group_by_code(cls, code: str) -> Optional[DeviceGroupDict]:
        """根据编码获取设备组"""
        try:
            return DeviceGroupDao.get_group_by_code(code)
        except Exception as e:
            log.error(f"获取设备组失败: {e}")
            return None

    @classmethod
    def create_group(
        cls,
        code: str,
        name: str,
        parent_id: Optional[int] = None,
        description: Optional[str] = None,
    ) -> int:
        """创建设备组
        
        Returns:
            新设备组ID，失败返回 -1
        """
        try:
            # 检查编码是否重复
            existing = DeviceGroupDao.get_group_by_code(code)
            if existing:
                log.error(f"设备组编码已存在: {code}")
                return -1
            return DeviceGroupDao.create_group(code, name, parent_id, description)
        except Exception as e:
            log.error(f"创建设备组失败: {e}")
            return -1

    @classmethod
    def update_group(cls, group_id: int, **kwargs) -> bool:
        """更新设备组"""
        try:
            return DeviceGroupDao.update_group(group_id, **kwargs)
        except Exception as e:
            log.error(f"更新设备组失败: {e}")
            return False

    @classmethod
    def delete_group(cls, group_id: int, cascade: bool = False) -> bool:
        """删除设备组
        
        Args:
            group_id: 设备组ID
            cascade: 是否级联删除子组，False时将子组和设备移至未分组
        """
        try:
            return DeviceGroupDao.delete_group(group_id, cascade)
        except Exception as e:
            log.error(f"删除设备组失败: {e}")
            return False

    @classmethod
    def add_device_to_group(cls, device_id: int, group_id: int) -> bool:
        """将设备添加到设备组"""
        try:
            return DeviceGroupDao.add_device_to_group(device_id, group_id)
        except Exception as e:
            log.error(f"添加设备到设备组失败: {e}")
            return False

    @classmethod
    def remove_device_from_group(cls, device_id: int) -> bool:
        """将设备从设备组移除"""
        try:
            return DeviceGroupDao.remove_device_from_group(device_id)
        except Exception as e:
            log.error(f"从设备组移除设备失败: {e}")
            return False

    @classmethod
    def move_devices_to_group(cls, device_ids: List[int], group_id: Optional[int]) -> int:
        """批量移动设备到指定设备组
        
        Args:
            device_ids: 设备ID列表
            group_id: 目标设备组ID，None表示移至未分组
            
        Returns:
            成功移动的设备数量
        """
        try:
            return DeviceGroupDao.move_devices_to_group(device_ids, group_id)
        except Exception as e:
            log.error(f"批量移动设备失败: {e}")
            return 0

    @classmethod
    def get_devices_by_group(cls, group_id: int) -> List[dict]:
        """获取指定设备组内的设备"""
        try:
            return DeviceGroupDao.get_devices_by_group(group_id)
        except Exception as e:
            log.error(f"获取设备组内设备失败: {e}")
            return []

    @classmethod
    def get_ungrouped_devices(cls) -> List[dict]:
        """获取未分组设备"""
        try:
            return DeviceGroupDao.get_ungrouped_devices()
        except Exception as e:
            log.error(f"获取未分组设备失败: {e}")
            return []

    @classmethod
    def update_group_status(cls, group_id: int, status: int) -> bool:
        """更新设备组状态"""
        try:
            return DeviceGroupDao.update_group_status(group_id, status)
        except Exception as e:
            log.error(f"更新设备组状态失败: {e}")
            return False
