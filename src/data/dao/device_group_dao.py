"""
设备组数据访问层
提供设备组的 CRUD 操作，支持多层嵌套结构
"""

from src.data.controller.db import local_session
from src.data.log import log
from src.data.model.channel import Channel
from src.data.model.device import Device
from src.data.model.device_group import DeviceGroup, DeviceGroupDict


class DeviceGroupDao:
    """设备组数据访问对象"""

    def __init__(self):
        pass

    @classmethod
    def get_all_groups(cls) -> list[DeviceGroupDict]:
        """获取所有设备组（按 ID 排序）"""
        try:
            with local_session() as session, session.begin():
                result = session.query(DeviceGroup).where(DeviceGroup.enable).order_by(DeviceGroup.id).all()
                return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取设备组列表失败: {str(e)}")
            raise e

    @classmethod
    def get_root_groups(cls) -> list[DeviceGroupDict]:
        """获取顶级设备组（parent_id 为 NULL）"""
        try:
            with local_session() as session, session.begin():
                result = (
                    session.query(DeviceGroup)
                    .where(DeviceGroup.enable, DeviceGroup.parent_id.is_(None))
                    .order_by(DeviceGroup.id)
                    .all()
                )
                return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取顶级设备组失败: {str(e)}")
            raise e

    @classmethod
    def get_children_groups(cls, parent_id: int) -> list[DeviceGroupDict]:
        """获取子设备组"""
        try:
            with local_session() as session, session.begin():
                result = (
                    session.query(DeviceGroup)
                    .where(DeviceGroup.enable, DeviceGroup.parent_id == parent_id)
                    .order_by(DeviceGroup.id)
                    .all()
                )
                return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取子设备组失败: {str(e)}")
            raise e

    @classmethod
    def get_group_tree(cls) -> list[dict]:
        """获取设备组树形结构（包含子组和设备）"""
        try:
            with local_session() as session, session.begin():
                # 获取所有顶级设备组
                root_groups = (
                    session.query(DeviceGroup)
                    .where(DeviceGroup.enable, DeviceGroup.parent_id.is_(None))
                    .order_by(DeviceGroup.id)
                    .all()
                )
                return [group.to_tree_dict() for group in root_groups]
        except Exception as e:
            log.error(f"获取设备组树失败: {str(e)}")
            raise e

    @classmethod
    def get_ungrouped_devices(cls) -> list[dict]:
        """获取未分组设备"""
        try:
            with local_session() as session, session.begin():
                result = session.query(Device).where(Device.enable, Device.group_id.is_(None)).order_by(Device.id).all()
                return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取未分组设备失败: {str(e)}")
            raise e

    @classmethod
    def get_group_by_id(cls, group_id: int) -> DeviceGroupDict | None:
        """根据ID获取设备组"""
        try:
            with local_session() as session, session.begin():
                result = session.query(DeviceGroup).where(DeviceGroup.id == group_id).first()
                return result.to_dict() if result else None
        except Exception as e:
            log.error(f"获取设备组失败: {str(e)}")
            raise e

    @classmethod
    def get_group_by_code(cls, code: str) -> DeviceGroupDict | None:
        """根据编码获取设备组"""
        try:
            with local_session() as session, session.begin():
                result = session.query(DeviceGroup).where(DeviceGroup.code == code).first()
                return result.to_dict() if result else None
        except Exception as e:
            log.error(f"获取设备组失败: {str(e)}")
            raise e

    @classmethod
    def create_group(
        cls,
        code: str,
        name: str,
        parent_id: int | None = None,
        description: str | None = None,
    ) -> int:
        """创建设备组

        Returns:
            新设备组ID
        """
        try:
            with local_session() as session, session.begin():
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
            with local_session() as session, session.begin():
                result = session.query(DeviceGroup).where(DeviceGroup.id == group_id).first()
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
        """硬删除设备组

        Args:
            group_id: 设备组ID
            cascade: 是否级联删除子组和设备；False 时提升子组并将设备移至未分组
        """
        try:
            with local_session() as session, session.begin():
                group = session.query(DeviceGroup).where(DeviceGroup.id == group_id).first()
                if not group:
                    return False

                if cascade:
                    group_ids = cls._get_descendant_group_ids(session, group_id)
                    session.query(Device).where(Device.group_id.in_(group_ids)).delete(synchronize_session=False)
                    for descendant_id in reversed(group_ids):
                        session.query(DeviceGroup).where(DeviceGroup.id == descendant_id).delete(
                            synchronize_session=False
                        )
                else:
                    session.query(DeviceGroup).where(DeviceGroup.parent_id == group_id).update(
                        {DeviceGroup.parent_id: group.parent_id}, synchronize_session=False
                    )
                    session.query(Device).where(Device.group_id == group_id).update(
                        {Device.group_id: None}, synchronize_session=False
                    )
                    session.query(DeviceGroup).where(DeviceGroup.id == group_id).delete(synchronize_session=False)

                return True
        except Exception as e:
            log.error(f"删除设备组失败: {str(e)}")
            raise e

    @classmethod
    def get_channel_ids_for_group_tree(cls, group_id: int) -> list[int]:
        """获取分组及全部子组内设备关联的通道 ID。"""
        try:
            with local_session() as session, session.begin():
                group_ids = cls._get_descendant_group_ids(session, group_id)
                if not group_ids:
                    return []
                rows = (
                    session.query(Channel.id)
                    .join(Device, Channel.device_id == Device.id)
                    .where(Device.group_id.in_(group_ids))
                    .all()
                )
                return [row[0] for row in rows]
        except Exception as e:
            log.error(f"获取设备组通道失败: {str(e)}")
            raise e

    @staticmethod
    def _get_descendant_group_ids(session, group_id: int) -> list[int]:
        """按父级在前的顺序返回指定分组及其全部子组 ID。"""
        rows = session.query(DeviceGroup.id, DeviceGroup.parent_id).all()
        children_by_parent: dict[int, list[int]] = {}
        existing_ids = {row.id for row in rows}
        if group_id not in existing_ids:
            return []
        for row in rows:
            if row.parent_id is not None:
                children_by_parent.setdefault(row.parent_id, []).append(row.id)

        result: list[int] = []
        stack = [group_id]
        while stack:
            current_id = stack.pop()
            result.append(current_id)
            stack.extend(reversed(children_by_parent.get(current_id, [])))
        return result

    @classmethod
    def add_device_to_group(cls, device_id: int, group_id: int) -> bool:
        """将设备添加到设备组"""
        try:
            with local_session() as session, session.begin():
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
            with local_session() as session, session.begin():
                device = session.query(Device).where(Device.id == device_id).first()
                if device:
                    device.group_id = None
                    return True
                return False
        except Exception as e:
            log.error(f"从设备组移除设备失败: {str(e)}")
            raise e

    @classmethod
    def move_devices_to_group(cls, device_ids: list[int], group_id: int | None) -> int:
        """批量移动设备到指定设备组

        Args:
            device_ids: 设备ID列表
            group_id: 目标设备组ID，None表示移至未分组

        Returns:
            成功移动的设备数量
        """
        try:
            with local_session() as session, session.begin():
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
    def get_devices_by_group(cls, group_id: int) -> list[dict]:
        """获取指定设备组内的设备"""
        try:
            with local_session() as session, session.begin():
                result = (
                    session.query(Device).where(Device.enable, Device.group_id == group_id).order_by(Device.id).all()
                )
                return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取设备组内设备失败: {str(e)}")
            raise e

    @classmethod
    def update_group_status(cls, group_id: int, status: int) -> bool:
        """更新设备组状态"""
        try:
            with local_session() as session, session.begin():
                result = session.query(DeviceGroup).where(DeviceGroup.id == group_id).first()
                if result:
                    result.status = status
                    return True
                return False
        except Exception as e:
            log.error(f"更新设备组状态失败: {str(e)}")
            raise e
