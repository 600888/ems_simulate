"""
设备数据访问层
提供设备的 CRUD 操作
"""

from typing import List, Optional

from src.data.model.device import Device, DeviceDict
from src.data.log import log
from src.data.controller.db import local_session


class DeviceDao:
    """设备数据访问对象"""

    def __init__(self):
        pass

    @classmethod
    def get_all_devices(cls) -> List[DeviceDict]:
        """获取所有设备"""
        try:
            with local_session() as session:
                with session.begin():
                    result = session.query(Device).where(Device.enable == True).all()
                    return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取设备列表失败: {str(e)}")
            raise e

    @classmethod
    def get_device_by_code(cls, code: str) -> Optional[DeviceDict]:
        """根据编码获取设备"""
        try:
            with local_session() as session:
                with session.begin():
                    result = session.query(Device).where(Device.code == code).first()
                    return result.to_dict() if result else None
        except Exception as e:
            log.error(f"获取设备失败: {str(e)}")
            raise e

    @classmethod
    def get_device_by_id(cls, device_id: int) -> Optional[DeviceDict]:
        """根据ID获取设备"""
        try:
            with local_session() as session:
                with session.begin():
                    result = session.query(Device).where(Device.id == device_id).first()
                    return result.to_dict() if result else None
        except Exception as e:
            log.error(f"获取设备失败: {str(e)}")
            raise e

    @classmethod
    def create_device(cls, code: str, name: str, device_type: int = 0, group_id: Optional[int] = None) -> int:
        """创建设备

        Returns:
            新设备ID
        """
        try:
            with local_session() as session:
                with session.begin():
                    device = Device(code=code, name=name, device_type=device_type, group_id=group_id)
                    session.add(device)
                    session.flush()
                    return device.id
        except Exception as e:
            log.error(f"创建设备失败: {str(e)}")
            raise e

    @classmethod
    def update_device(cls, device_id: int, **kwargs) -> bool:
        """更新设备"""
        try:
            with local_session() as session:
                with session.begin():
                    result = session.query(Device).where(Device.id == device_id).first()
                    if result:
                        for key, value in kwargs.items():
                            if hasattr(result, key):
                                setattr(result, key, value)
                        return True
                    return False
        except Exception as e:
            log.error(f"更新设备失败: {str(e)}")
            raise e

    @classmethod
    def delete_device(cls, device_id: int) -> bool:
        """删除设备（软删除）"""
        try:
            with local_session() as session:
                with session.begin():
                    result = session.query(Device).where(Device.id == device_id).first()
                    if result:
                        result.enable = False
                        return True
                    return False
        except Exception as e:
            log.error(f"删除设备失败: {str(e)}")
            raise e
