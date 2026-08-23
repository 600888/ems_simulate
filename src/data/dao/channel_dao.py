"""
通道数据访问层
提供通道的 CRUD 操作
"""

from src.data.controller.db import local_session
from src.data.log import log
from src.data.model.channel import Channel, ChannelDict


class ChannelDao:
    """通道数据访问对象"""

    def __init__(self):
        pass

    @classmethod
    def get_all_channels(cls) -> list[ChannelDict]:
        """获取所有通道（按 ID 排序）"""
        try:
            with local_session() as session, session.begin():
                result = session.query(Channel).where(Channel.enable).order_by(Channel.id).all()
                return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取通道列表失败: {str(e)}")
            raise e

    @classmethod
    def get_channels_by_device(cls, device_id: int) -> list[ChannelDict]:
        """根据设备ID获取通道列表"""
        try:
            with local_session() as session, session.begin():
                result = session.query(Channel).where(Channel.device_id == device_id, Channel.enable).all()
                return [item.to_dict() for item in result]
        except Exception as e:
            log.error(f"获取通道列表失败: {str(e)}")
            raise e

    @classmethod
    def get_channel_by_code(cls, code: str) -> ChannelDict | None:
        """根据编码获取通道"""
        try:
            with local_session() as session, session.begin():
                result = session.query(Channel).where(Channel.code == code).first()
                return result.to_dict() if result else None
        except Exception as e:
            log.error(f"获取通道失败: {str(e)}")
            raise e

    @classmethod
    def get_channel_by_id(cls, channel_id: int) -> ChannelDict | None:
        """根据ID获取通道（包含设备组ID）"""
        try:
            with local_session() as session, session.begin():
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
        device_id: int | None = None,
        protocol_type: int = 1,
        conn_type: int = 1,
        **kwargs,
    ) -> int:
        """创建通道

        Returns:
            新通道ID
        """
        try:
            with local_session() as session, session.begin():
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
        from src.data.model.device import Device

        try:
            with local_session() as session, session.begin():
                channel = session.query(Channel).where(Channel.id == channel_id).first()
                if channel:
                    # 1. 更新通道信息
                    for key, value in kwargs.items():
                        if hasattr(channel, key):
                            setattr(channel, key, value)

                    # 2. 同步更新关联的设备信息 (Name, Code)
                    if channel.device_id:
                        device = session.query(Device).where(Device.id == channel.device_id).first()
                        if device:
                            if "name" in kwargs:
                                device.name = kwargs["name"]
                            if "code" in kwargs:
                                device.code = kwargs["code"]
                            # IEC 61850: 同步 icd_path 到设备
                            if "icd_path" in kwargs:
                                device.icd_path = kwargs["icd_path"]
                            if "icd_file_hash" in kwargs:
                                device.icd_file_hash = kwargs["icd_file_hash"]
                    return True
                return False
        except Exception as e:
            log.error(f"更新通道失败: {str(e)}")
            raise e

    # ==== IEC 61850 ICD 路径管理 ====

    @classmethod
    def set_channel_icd_path(cls, channel_id: int, icd_path: str, file_hash: str = "") -> bool:
        """设置通道的 ICD 文件路径

        自动同步到关联的设备记录。
        """
        from src.data.model.device import Device

        try:
            with local_session() as session, session.begin():
                channel = session.query(Channel).where(Channel.id == channel_id).first()
                if not channel:
                    return False
                channel.icd_path = icd_path
                channel.icd_file_hash = file_hash
                # 同步到设备
                if channel.device_id:
                    device = session.query(Device).where(Device.id == channel.device_id).first()
                    if device:
                        device.icd_path = icd_path
                        device.icd_file_hash = file_hash
                return True
        except Exception as e:
            log.error(f"设置通道 ICD 路径失败: {str(e)}")
            raise e

    @classmethod
    def get_channel_icd_path(cls, channel_id: int) -> str | None:
        """获取通道的 ICD 文件路径"""
        try:
            with local_session() as session, session.begin():
                channel = session.query(Channel).where(Channel.id == channel_id).first()
                return channel.icd_path if channel else None
        except Exception as e:
            log.error(f"获取通道 ICD 路径失败: {str(e)}")
            return None

    @classmethod
    def clear_channel_icd_path(cls, channel_id: int) -> bool:
        """清除通道的 ICD 文件路径关联"""
        try:
            with local_session() as session, session.begin():
                channel = session.query(Channel).where(Channel.id == channel_id).first()
                if channel:
                    channel.icd_path = None
                    channel.icd_file_hash = None
                    return True
                return False
        except Exception as e:
            log.error(f"清除通道 ICD 路径失败: {str(e)}")
            raise e

    @classmethod
    def delete_channel(cls, channel_id: int) -> bool:
        """删除通道及关联测点（硬删除）"""
        from src.data.model.channel_configuration import ChannelProtocolParams, ChannelSecurityConfig
        from src.data.model.connection_session import ConnectionSession
        from src.data.model.device import Device
        from src.data.model.goose_publisher import GooseEntry, GoosePublisher
        from src.data.model.goose_receiver import GooseReceiverConfig, GooseSubscriptionConfig
        from src.data.model.point_mapping import PointMapping
        from src.data.model.point_yc import PointYc
        from src.data.model.point_yk import PointYk
        from src.data.model.point_yt import PointYt
        from src.data.model.point_yx import PointYx
        from src.data.model.slave import Slave

        try:
            with local_session() as session, session.begin():
                channel = session.query(Channel).where(Channel.id == channel_id).first()
                if not channel:
                    return False
                device_id = channel.device_id

                # 控制点可能引用遥信/遥测点，必须先删除依赖方。
                session.query(PointYk).where(PointYk.channel_id == channel_id).delete()
                session.query(PointYt).where(PointYt.channel_id == channel_id).delete()
                session.query(PointYc).where(PointYc.channel_id == channel_id).delete()
                session.query(PointYx).where(PointYx.channel_id == channel_id).delete()

                session.query(Slave).where(Slave.channel_id == channel_id).delete()
                session.query(PointMapping).where(PointMapping.device_name == channel.name).delete()

                # 显式清理所有不带数据库级联的通道配置，兼容旧版 SQLite 数据库。
                session.query(ChannelProtocolParams).where(ChannelProtocolParams.channel_id == channel_id).delete()
                session.query(ChannelSecurityConfig).where(ChannelSecurityConfig.channel_id == channel_id).delete()
                session.query(ConnectionSession).where(ConnectionSession.channel_id == channel_id).delete()

                publisher_ids = session.query(GoosePublisher.id).where(GoosePublisher.channel_id == channel_id)
                session.query(GooseEntry).where(GooseEntry.publisher_id.in_(publisher_ids)).delete(
                    synchronize_session=False
                )
                session.query(GoosePublisher).where(GoosePublisher.channel_id == channel_id).delete(
                    synchronize_session=False
                )

                receiver_ids = session.query(GooseReceiverConfig.id).where(GooseReceiverConfig.channel_id == channel_id)
                session.query(GooseSubscriptionConfig).where(
                    GooseSubscriptionConfig.receiver_id.in_(receiver_ids)
                ).delete(synchronize_session=False)
                session.query(GooseReceiverConfig).where(GooseReceiverConfig.channel_id == channel_id).delete(
                    synchronize_session=False
                )

                # channel 持有指向 device 的外键，因此必须先删通道、再删设备。
                session.query(Channel).where(Channel.id == channel_id).delete(synchronize_session=False)
                session.flush()
                if device_id is not None:
                    has_other_channels = (
                        session.query(Channel.id).where(Channel.device_id == device_id).first() is not None
                    )
                    if not has_other_channels:
                        session.query(Device).where(Device.id == device_id).delete(synchronize_session=False)
                return True
        except Exception as e:
            log.error(f"删除通道失败: {str(e)}")
            raise e
