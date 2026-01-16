from typing import List
from src.data.dao.channel_dao import ChannelDao
from src.enums.channel import Channel, NetConfig
from src.enums.connection_type import ConnectionType
from src.enums.modbus_def import ProtocolType, get_protocol_type_by_value
from src.data.log import log


class ChannelService:
    def __init__(self):
        pass

    @classmethod
    def get_channel_list(cls) -> List[Channel]:
        try:
            result = ChannelDao().get_channel_list()
            channel_list = []
            for item in result:
                connection_type = ConnectionType(item["dev_type"])
                protocol = item["protocol_type"]

                if connection_type == ConnectionType.Serial:
                    if protocol == 0:
                        protocol_type = ProtocolType.ModbusRtu
                        continue
                    elif protocol == 1:
                        protocol_type = ProtocolType.ModbusRtuOverTcp
                    else:
                        continue
                else:
                    if protocol == 1:
                        protocol_type = ProtocolType.ModbusTcp
                    elif protocol == 2:
                        protocol_type = ProtocolType.ModbusTcpClient
                    elif protocol == 6:
                        protocol_type = ProtocolType.Dlt645Server
                    elif (
                        protocol == 10
                    ):  # 这里和数据库里面相反,EMS作为客户端的时候,模拟设备作为服务服务端
                        protocol_type = ProtocolType.Iec104Server
                    elif protocol == 9:
                        protocol_type = ProtocolType.Iec104Client

                # 只处理TCP的情况
                # 截取冒号后的端口号
                addr = item["remote_addr"]
                ip = addr[: addr.find(":")]
                port = addr[addr.find(":") + 1 :]

                channel = Channel(
                    id=item["id"],
                    code=item["code"],
                    name=item["name"],
                    protocol_type=protocol_type,
                    connection_type=connection_type,
                    net_config=NetConfig(ip=ip, port=port),
                )
                channel_list.append(channel)
                log.debug(f"获取通道: {channel}")
            return channel_list
        except Exception as e:
            log.error(f"获取通道列表失败: {e}")
            return []
