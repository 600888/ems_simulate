"""
设备组数据访问层
提供设备组的 CRUD 操作，支持多层嵌套结构
"""

from typing import List, Optional

from src.data.model.device_group import DeviceGroup, DeviceGroupDict
from src.data.model.device import Device
from src.data.log import log
from src.data.controller.db import local_session


class DeviceGroupDao:
    """设备组数据访问对象"""

    def __init__(self):
        pass

    @classmethod
    def get_all_groups(cls) -> List[DeviceGroupDict]:
        """获取所有设备组（按 ID 排序）"""
        try:
            with local_session() as session:
                with session.begin():
                    result = (
                        session.query(DeviceGroup)
                        .where(DeviceGroup.enable == True)
                        .order_by(DeviceGroup.id)
                        .all()
                    )
                    return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取设备组列表失败: {str(e)}")
            raise e

    @classmethod
    def get_root_groups(cls) -> List[DeviceGroupDict]:
        """获取顶级设备组（parent_id 为 NULL）"""
        try:
            with local_session() as session:
                with session.begin():
                    result = (
                        session.query(DeviceGroup)
                        .where(
                            DeviceGroup.enable == True,
                            DeviceGroup.parent_id == None
                        )
                        .order_by(DeviceGroup.id)
                        .all()
                    )
                    return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取顶级设备组失败: {str(e)}")
            raise e

    @classmethod
    def get_children_groups(cls, parent_id: int) -> List[DeviceGroupDict]:
        """获取子设备组"""
        try:
            with local_session() as session:
                with session.begin():
                    result = (
                        session.query(DeviceGroup)
                        .where(
                            DeviceGroup.enable == True,
                            DeviceGroup.parent_id == parent_id
                        )
                        .order_by(DeviceGroup.id)
                        .all()
                    )
                    return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取子设备组失败: {str(e)}")
            raise e

    @classmethod
    def get_group_tree(cls) -> List[dict]:
        """获取设备组树形结构（包含子组和设备）"""
        try:
            with local_session() as session:
                with session.begin():
                    # 获取所有顶级设备组
                    root_groups = (
                        session.query(DeviceGroup)
                        .where(
                            DeviceGroup.enable == True,
                            DeviceGroup.parent_id == None
                        )
                        .order_by(DeviceGroup.id)
                        .all()
                    )
                    return [group.to_tree_dict() for group in root_groups]
        except Exception as e:
            log.error(f"获取设备组树失败: {str(e)}")
            raise e

    @classmethod
    def get_ungrouped_devices(cls) -> List[dict]:
        """获取未分组设备"""
        try:
            with local_session() as session:
                with session.begin():
                    result = (
                        session.query(Device)
                        .where(
                            Device.enable == True,
                            Device.group_id == None
                        )
                        .order_by(Device.id)
                        .all()
                    )
                    return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取未分组设备失败: {str(e)}")
            raise e

    @classmethod
    def get_group_by_id(cls, group_id: int) -> Optional[DeviceGroupDict]:
        """根据ID获取设备组"""
        try:
            with local_session() as session:
                with session.begin():
                    result = (
                        session.query(DeviceGroup)
                        .where(DeviceGroup.id == group_id)
                        .first()
                    )
                    return result.to_dict() if result else None
        except Exception as e:
            log.error(f"获取设备组失败: {str(e)}")
            raise e

    @classmethod
    def get_group_by_code(cls, code: str) -> Optional[DeviceGroupDict]:
        """根据编码获取设备组"""
        try:
            with local_session() as session:
                with session.begin():
                    result = (
                        session.query(DeviceGroup)
                        .where(DeviceGroup.code == code)
                        .first()
                    )
                    return result.to_dict() if result else None
        except Exception as e:
            log.error(f"获取设备组失败: {str(e)}")
            raise e

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
            新设备组ID
        """
        try:
            with local_session() as session:
                with session.begin():
                    group = DeviceGroup(
                        code=code,
                        name=name,
                        parent_id=parent_id,
                        description=description,
                    )
                    session.add(group)
                    session.flush()
                    return group.id
        except Exception as e:
            log.error(f"创建设备组失败: {str(e)}")
            raise e

    @classmethod
    def update_group(cls, group_id: int, **kwargs) -> bool:
        """更新设备组"""
        try:
            with local_session() as session:
                with session.begin():
                    result = (
                        session.query(DeviceGroup)
                        .where(DeviceGroup.id == group_id)
                        .first()
                    )
                    if result:
                        for key, value in kwargs.items():
                            if hasattr(result, key):
                                setattr(result, key, value)
                        return True
                    return False
        except Exception as e:
            log.error(f"更新设备组失败: {str(e)}")
            raise e

    @classmethod
    def delete_group(cls, group_id: int, cascade: bool = False) -> bool:
        """删除设备组
        
        Args:
            group_id: 设备组ID
            cascade: 是否级联删除子组和设备，False时将子组和设备移至未分组
        """
        try:
            with local_session() as session:
                with session.begin():
                    group = (
                        session.query(DeviceGroup)
                        .where(DeviceGroup.id == group_id)
                        .first()
                    )
                    if not group:
                        return False
                    
                    if cascade:
                        # 级联软删除
                        group.enable = False
                        # 递归删除子组
                        for child in group.children:
                            cls._soft_delete_recursive(session, child)
                    else:
                        # 将子组移至父级（或变为顶级）
                        for child in group.children:
                            child.parent_id = group.parent_id
                        # 将组内设备设为未分组
                        for device in group.devices:
                            device.group_id = None
                        # 软删除该组
                        group.enable = False
                    
                    return True
        except Exception as e:
            log.error(f"删除设备组失败: {str(e)}")
            raise e

    @classmethod
    def _soft_delete_recursive(cls, session, group: DeviceGroup):
        """递归软删除设备组及其子组"""
        group.enable = False
        for child in group.children:
            cls._soft_delete_recursive(session, child)

    @classmethod
    def add_device_to_group(cls, device_id: int, group_id: int) -> bool:
        """将设备添加到设备组"""
        try:
            with local_session() as session:
                with session.begin():
                    device = session.query(Device).where(Device.id == device_id).first()
                    if device:
                        device.group_id = group_id
                        return True
                    return False
        except Exception as e:
            log.error(f"添加设备到设备组失败: {str(e)}")
            raise e

    @classmethod
    def remove_device_from_group(cls, device_id: int) -> bool:
        """将设备从设备组移除（设为未分组）"""
        try:
            with local_session() as session:
                with session.begin():
                    device = session.query(Device).where(Device.id == device_id).first()
                    if device:
                        device.group_id = None
                        return True
                    return False
        except Exception as e:
            log.error(f"从设备组移除设备失败: {str(e)}")
            raise e

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
            with local_session() as session:
                with session.begin():
                    count = (
                        session.query(Device)
                        .where(Device.id.in_(device_ids))
                        .update({Device.group_id: group_id}, synchronize_session=False)
                    )
                    return count
        except Exception as e:
            log.error(f"批量移动设备失败: {str(e)}")
            raise e

    @classmethod
    def get_devices_by_group(cls, group_id: int) -> List[dict]:
        """获取指定设备组内的设备"""
        try:
            with local_session() as session:
                with session.begin():
                    result = (
                        session.query(Device)
                        .where(
                            Device.enable == True,
                            Device.group_id == group_id
                        )
                        .order_by(Device.id)
                        .all()
                    )
                    return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取设备组内设备失败: {str(e)}")
            raise e

    @classmethod
    def update_group_status(cls, group_id: int, status: int) -> bool:
        """更新设备组状态"""
        try:
            with local_session() as session:
                with session.begin():
                    result = (
                        session.query(DeviceGroup)
                        .where(DeviceGroup.id == group_id)
                        .first()
                    )
                    if result:
                        result.status = status
                        return True
                    return False
        except Exception as e:
            log.error(f"更新设备组状态失败: {str(e)}")
            raise e
