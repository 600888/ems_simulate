"""
通道服务模块
提供通道的业务逻辑
"""

from src.data.dao.channel_dao import ChannelDao
from src.data.log import log
from src.data.model.channel import ChannelDict
from src.enums.modbus_def import ProtocolType


class ChannelService:
    """通道服务类"""

    def __init__(self):
        pass

    @classmethod
    def get_all_channels(cls) -> list[ChannelDict]:
        """获取所有启用的通道"""
        try:
            return ChannelDao.get_all_channels()
        except Exception as e:
            log.error(f"获取通道列表失败: {e}")
            return []

    @classmethod
    def get_channels_by_device(cls, device_id: int) -> list[ChannelDict]:
        """根据设备ID获取通道列表"""
        try:
            return ChannelDao.get_channels_by_device(device_id)
        except Exception as e:
            log.error(f"获取通道列表失败: {e}")
            return []

    @classmethod
    def get_channel_by_code(cls, code: str) -> ChannelDict | None:
        """根据编码获取通道"""
        try:
            return ChannelDao.get_channel_by_code(code)
        except Exception as e:
            log.error(f"获取通道失败: {e}")
            return None

    @classmethod
    def get_channel_by_id(cls, channel_id: int) -> ChannelDict | None:
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
        # 连接类型与协议映射
        mapping = {
            # 串口主站
            (0, 0): ProtocolType.ModbusRtuClient,
            (0, 3): ProtocolType.Dlt645Client,
            # TCP 客户端
            (1, 1): ProtocolType.ModbusTcpClient,
            (1, 2): ProtocolType.Iec104Client,
            (1, 3): ProtocolType.Dlt645Client,
            (1, 4): ProtocolType.Iec61850Client,
            # TCP 服务端
            (2, 1): ProtocolType.ModbusTcp,
            (2, 2): ProtocolType.Iec104Server,
            (2, 3): ProtocolType.Dlt645Server,
            (2, 4): ProtocolType.Iec61850Server,
        }
        result = mapping.get((conn_type, protocol))
        if result is not None:
            return result

        # 串口从站（服务端模式 - 被采集）
        elif conn_type == 3:
            if protocol == 0:
                return ProtocolType.ModbusRtuServer  # Modbus RTU 从站（服务端）
            elif protocol == 3:
                return ProtocolType.Dlt645Server  # DLT645 从站模拟电表

        return ProtocolType.ModbusTcp

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
        """创建通道"""
        try:
            return ChannelDao.create_channel(code, name, device_id, protocol_type, conn_type, **kwargs)
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
