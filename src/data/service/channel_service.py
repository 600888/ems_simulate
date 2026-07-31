"""
通道服务模块
提供通道的业务逻辑
"""

from typing import Any

from src.data.controller.db import local_session
from src.data.dao.channel_dao import ChannelDao
from src.data.log import log
from src.data.model.channel import Channel, ChannelDict
from src.data.model.channel_configuration import ChannelProtocolParams
from src.data.model.device import Device
from src.device.protocol.runtime_config import normalize_protocol_params
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
    def provision_channel(
        cls,
        *,
        code: str,
        name: str,
        group_id: int | None,
        protocol_type: int,
        conn_type: int,
        protocol_params: dict[str, Any] | None,
        protocol_schema_version: int = 1,
        **channel_values,
    ) -> tuple[int, int]:
        """在一个事务内创建设备、通道及协议配置。"""
        normalized = normalize_protocol_params(protocol_type, conn_type, protocol_params)
        with local_session() as session, session.begin():
            device = Device(
                code=code,
                name=name,
                device_type=0,
                group_id=group_id,
            )
            session.add(device)
            session.flush()

            channel = Channel(
                code=code,
                name=name,
                device_id=device.id,
                protocol_type=protocol_type,
                conn_type=conn_type,
                **channel_values,
            )
            session.add(channel)
            session.flush()
            session.add(
                ChannelProtocolParams(
                    channel_id=channel.id,
                    protocol_type=protocol_type,
                    conn_type=conn_type,
                    schema_version=protocol_schema_version,
                    params_json=normalized,
                )
            )
            return device.id, channel.id

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

    # ==== IEC 61850 ICD 路径管理 ====

    @classmethod
    def set_icd_path(cls, channel_id: int, icd_path: str, file_hash: str = "") -> bool:
        """设置通道的 ICD 文件路径

        自动同步到关联的设备记录。
        """
        try:
            return ChannelDao.set_channel_icd_path(channel_id, icd_path, file_hash)
        except Exception as e:
            log.error(f"设置通道 ICD 路径失败: {e}")
            return False

    @classmethod
    def get_icd_path(cls, channel_id: int) -> str | None:
        """获取通道的 ICD 文件路径"""
        try:
            return ChannelDao.get_channel_icd_path(channel_id)
        except Exception as e:
            log.error(f"获取通道 ICD 路径失败: {e}")
            return None

    @classmethod
    def clear_icd_path(cls, channel_id: int) -> bool:
        """清除通道的 ICD 文件路径关联"""
        try:
            return ChannelDao.clear_channel_icd_path(channel_id)
        except Exception as e:
            log.error(f"清除通道 ICD 路径失败: {e}")
            return False
