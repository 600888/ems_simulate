from typing import Optional
from pydantic import BaseModel

from src.enums.connection_type import ConnectionType
from src.enums.modbus_def import ProtocolType


class NetConfig(BaseModel):
    ip: str
    port: int


class RtuConfig(BaseModel):
    port: int  # 串口号
    baud_rate: int  # 波特率
    data_bits: int  # 数据位
    stop_bits: int  # 停止位
    parity: str  # 校验位


class Channel(BaseModel):
    id: int
    code: str
    name: str
    connection_type: ConnectionType
    protocol_type: ProtocolType
    net_config: Optional[NetConfig] = None
    rtu_config: Optional[RtuConfig] = None

    def __repr__(self):
        return f"Channel(id={self.id}, code={self.code}, name={self.name}, connection_type={self.connection_type}, protocol_type={self.protocol_type}, net_config={self.net_config}, rtu_config={self.rtu_config})"
