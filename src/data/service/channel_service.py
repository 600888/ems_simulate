"""
通道服务模块
提供通道的业务逻辑
"""

from typing import List, Optional
from src.data.dao.channel_dao import ChannelDao
from src.data.model.channel import ChannelDict
from src.enums.modbus_def import ProtocolType
from src.data.log import log


class ChannelService:
    """通道服务类"""

    def __init__(self):
        pass

    @classmethod
    def get_all_channels(cls) -> List[ChannelDict]:
        """获取所有启用的通道"""
        try:
            return ChannelDao.get_all_channels()
        except Exception as e:
            log.error(f"获取通道列表失败: {e}")
            return []

    @classmethod
    def get_channels_by_device(cls, device_id: int) -> List[ChannelDict]:
        """根据设备ID获取通道列表"""
        try:
            return ChannelDao.get_channels_by_device(device_id)
        except Exception as e:
            log.error(f"获取通道列表失败: {e}")
            return []

    @classmethod
    def get_channel_by_code(cls, code: str) -> Optional[ChannelDict]:
        """根据编码获取通道"""
        try:
            return ChannelDao.get_channel_by_code(code)
        except Exception as e:
            log.error(f"获取通道失败: {e}")
            return None

    @classmethod
    def get_channel_by_id(cls, channel_id: int) -> Optional[ChannelDict]:
        """根据ID获取通道"""
        try:
            return ChannelDao.get_channel_by_id(channel_id)
        except Exception as e:
            log.error(f"获取通道失败: {e}")
            return None

    @classmethod
    def get_protocol_type(cls, channel: ChannelDict) -> ProtocolType:
        """根据通道配置获取协议类型"""
        protocol = channel.get("protocol_type", 1)
        conn_type = channel.get("conn_type", 1)

        # 串口主站（客户端模式 - 主动采集）
        if conn_type == 0:
            if protocol == 0:
                return ProtocolType.ModbusRtu  # Modbus RTU 主站
            elif protocol == 3:
                return ProtocolType.Dlt645Client  # DLT645 主站采集电表

        # TCP 客户端
        elif conn_type == 1:
            if protocol == 1:
                return ProtocolType.ModbusTcpClient
            elif protocol == 2:
                return ProtocolType.Iec104Client
            elif protocol == 3:
                return ProtocolType.Dlt645Client

        # TCP 服务端
        elif conn_type == 2:
            if protocol == 1:
                return ProtocolType.ModbusTcp
            elif protocol == 2:
                return ProtocolType.Iec104Server
            elif protocol == 3:
                return ProtocolType.Dlt645Server

        # 串口从站（服务端模式 - 被采集）
        elif conn_type == 3:
            if protocol == 0:
                return ProtocolType.ModbusRtu  # Modbus RTU 从站（目前共用同一类型）
            elif protocol == 3:
                return ProtocolType.Dlt645Server  # DLT645 从站模拟电表

        return ProtocolType.ModbusTcp

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
        """创建通道"""
        try:
            return ChannelDao.create_channel(
                code, name, device_id, protocol_type, conn_type, **kwargs
            )
        except Exception as e:
            log.error(f"创建通道失败: {e}")
            return -1

    @classmethod
    def update_channel(cls, channel_id: int, **kwargs) -> bool:
        """更新通道"""
        try:
            return ChannelDao.update_channel(channel_id, **kwargs)
        except Exception as e:
            log.error(f"更新通道失败: {e}")
            return False

    @classmethod
    def delete_channel(cls, channel_id: int) -> bool:
        """删除通道"""
        try:
            return ChannelDao.delete_channel(channel_id)
        except Exception as e:
            log.error(f"删除通道失败: {e}")
            return False
