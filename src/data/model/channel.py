from typing import Optional, TypedDict
from sqlalchemy import Integer, String, Boolean
from sqlalchemy.orm import mapped_column, Mapped

from src.data.model.base import Base


class ChannelDict(TypedDict):
    id: int
    code: str
    name: str
    enable: bool
    dev_type: int
    protocol_type: int
    local_addr: Optional[str]  # 如果可为 None
    remote_addr: str
    rtu_addr: int
    stop_time: int
    error_limit: int
    time_out: int


# 通道 数据表
class Channel(Base):
    __tablename__ = "channel"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="通道id")
    code: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True, comment="通道编码"
    )
    name: Mapped[str] = mapped_column(String(64), comment="通道名称")
    enable: Mapped[bool] = mapped_column(Boolean, comment="是否使用")
    dev_type: Mapped[int] = mapped_column(
        Integer,
        server_default="1",
        comment="通道类型, 0:串口, 1:TCP客户端, 2:TCP服务端, 3:无效",
    )
    protocol_type: Mapped[int] = mapped_column(
        Integer,
        comment="规约类型, 0:ModbusRtu, 1:ModbusTcp, 2:ModbusIcc,"
        "3:IEC_103, 4:IEC_104, 5:IEC_104_ICC, 6:DLT645_2007"
        ", 7:MMS_61850, 8:GOOSE_61850, 9:104服务端, 10:104客户端",
    )
    local_addr: Mapped[str] = mapped_column(
        String(32), nullable=True, comment="本地地址，格式为端口号"
    )
    remote_addr: Mapped[str] = mapped_column(String(32), comment="远端地址")
    rtu_addr: Mapped[int] = mapped_column(
        Integer, server_default="-1", comment="远程终端设备号"
    )
    stop_time: Mapped[int] = mapped_column(
        Integer, server_default="60", comment="停止时间(s)"
    )
    error_limit: Mapped[int] = mapped_column(
        Integer, server_default="15", comment="错误限制(s)"
    )
    time_out: Mapped[int] = mapped_column(
        Integer, server_default="5", comment="超时时间(s)"
    )
    __table_args__ = {"comment": "通道数据表"}

    def to_dict(self) -> ChannelDict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
