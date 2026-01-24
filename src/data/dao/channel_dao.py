"""
通道数据访问层
提供通道的 CRUD 操作
"""

from typing import List, Optional

from src.data.model.channel import Channel, ChannelDict
from src.data.log import log
from src.data.controller.db import local_session


class ChannelDao:
    """通道数据访问对象"""

    def __init__(self):
        pass

    @classmethod
    def get_all_channels(cls) -> List[ChannelDict]:
        """获取所有通道（按 ID 排序）"""
        try:
            with local_session() as session:
                with session.begin():
                    result = session.query(Channel).where(Channel.enable == True).order_by(Channel.id).all()
                    return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取通道列表失败: {str(e)}")
            raise e

    @classmethod
    def get_channels_by_device(cls, device_id: int) -> List[ChannelDict]:
        """根据设备ID获取通道列表"""
        try:
            with local_session() as session:
                with session.begin():
                    result = (
                        session.query(Channel)
                        .where(Channel.device_id == device_id, Channel.enable == True)
                        .all()
                    )
                    return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取通道列表失败: {str(e)}")
            raise e

    @classmethod
    def get_channel_by_code(cls, code: str) -> Optional[ChannelDict]:
        """根据编码获取通道"""
        try:
            with local_session() as session:
                with session.begin():
                    result = session.query(Channel).where(Channel.code == code).first()
                    return result.to_dict() if result else None
        except Exception as e:
            log.error(f"获取通道失败: {str(e)}")
            raise e

    @classmethod
    def get_channel_by_id(cls, channel_id: int) -> Optional[ChannelDict]:
        """根据ID获取通道（包含设备组ID）"""
        try:
            with local_session() as session:
                with session.begin():
                    result = session.query(Channel).where(Channel.id == channel_id).first()
                    if result:
                        data = result.to_dict()
                        # 从关联的 Device 获取 group_id
                        if result.device:
                            data["group_id"] = result.device.group_id
                        else:
                            data["group_id"] = None
                        return data
                    return None
        except Exception as e:
            log.error(f"获取通道失败: {str(e)}")
            raise e

    @classmethod
    def create_channel(
        cls,
        code: str,
        name: str,
        device_id: Optional[int] = None,
        protocol_type: int = 1,
        conn_type: int = 1,
        **kwargs,
    ) -> int:
        """创建通道

        Returns:
            新通道ID
        """
        try:
            with local_session() as session:
                with session.begin():
                    channel = Channel(
                        code=code,
                        name=name,
                        device_id=device_id,
                        protocol_type=protocol_type,
                        conn_type=conn_type,
                        **kwargs,
                    )
                    session.add(channel)
                    session.flush()
                    return channel.id
        except Exception as e:
            log.error(f"创建通道失败: {str(e)}")
            raise e

    @classmethod
    def update_channel(cls, channel_id: int, **kwargs) -> bool:
        """更新通道"""
        try:
            with local_session() as session:
                with session.begin():
                    result = session.query(Channel).where(Channel.id == channel_id).first()
                    if result:
                        for key, value in kwargs.items():
                            if hasattr(result, key):
                                setattr(result, key, value)
                        return True
                    return False
        except Exception as e:
            log.error(f"更新通道失败: {str(e)}")
            raise e

    @classmethod
    def delete_channel(cls, channel_id: int) -> bool:
        """删除通道及关联测点（硬删除）"""
        from src.data.model.point_yc import PointYc
        from src.data.model.point_yx import PointYx
        from src.data.model.point_yk import PointYk
        from src.data.model.point_yt import PointYt
        
        try:
            with local_session() as session:
                with session.begin():
                    # 先删除关联的测点
                    session.query(PointYc).where(PointYc.channel_id == channel_id).delete()
                    session.query(PointYx).where(PointYx.channel_id == channel_id).delete()
                    session.query(PointYk).where(PointYk.channel_id == channel_id).delete()
                    session.query(PointYt).where(PointYt.channel_id == channel_id).delete()
                    
                    # 再删除通道
                    result = session.query(Channel).where(Channel.id == channel_id).first()
                    if result:
                        session.delete(result)
                        return True
                    return False
        except Exception as e:
            log.error(f"删除通道失败: {str(e)}")
            raise e
