"""
通道表模型
管理设备通信通道配置，支持 TCP 和串口
"""

from typing import TypedDict, Optional
from sqlalchemy import Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import mapped_column, Mapped, relationship

from src.data.model.base import Base


class ChannelDict(TypedDict):
    """通道字典类型"""
    id: int
    code: str
    name: str
    device_id: Optional[int]
    protocol_type: int
    conn_type: int
    # TCP 配置
    ip: Optional[str]
    port: Optional[int]
    # 串口配置
    com_port: Optional[str]
    baud_rate: Optional[int]
    data_bits: Optional[int]
    stop_bits: Optional[int]
    parity: Optional[str]
    # 通用配置
    rtu_addr: str
    timeout: int
    enable: bool


class Channel(Base):
    """通道表 - 支持 TCP 和串口通信"""
    __tablename__ = "channel"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="通道ID"
    )
    code: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True, comment="通道编码"
    )
    name: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="通道名称"
    )
    device_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("device.id"), nullable=True, comment="所属设备ID"
    )
    protocol_type: Mapped[int] = mapped_column(
        Integer,
        server_default="1",
        comment="协议类型: 0:ModbusRtu, 1:ModbusTcp, 2:IEC104, 3:DLT645",
    )
    conn_type: Mapped[int] = mapped_column(
        Integer,
        server_default="1",
        comment="连接类型: 0:串口, 1:TCP客户端, 2:TCP服务端",
    )

    # TCP 配置
    ip: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, comment="IP地址(TCP模式)"
    )
    port: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="端口号(TCP模式)"
    )

    # 串口配置
    com_port: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True, comment="串口号(如COM1)"
    )
    baud_rate: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default="9600", comment="波特率"
    )
    data_bits: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default="8", comment="数据位"
    )
    stop_bits: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default="1", comment="停止位"
    )
    parity: Mapped[Optional[str]] = mapped_column(
        String(1), nullable=True, server_default="N", comment="校验位: N/E/O"
    )

    # 通用配置
    rtu_addr: Mapped[str] = mapped_column(
        String(16), server_default="1", comment="电表地址(DLT645)"
    )
    timeout: Mapped[int] = mapped_column(
        Integer, server_default="5", comment="超时时间(秒)"
    )
    enable: Mapped[bool] = mapped_column(
        Boolean, server_default="1", comment="是否启用"
    )

    # 关系
    device = relationship("Device", back_populates="channels")
    # 四类测点关系
    points_yc = relationship("PointYc", backref="channel", foreign_keys="PointYc.channel_id")
    points_yx = relationship("PointYx", backref="channel", foreign_keys="PointYx.channel_id")
    points_yk = relationship("PointYk", backref="channel", foreign_keys="PointYk.channel_id")
    points_yt = relationship("PointYt", backref="channel", foreign_keys="PointYt.channel_id")
    slaves = relationship("Slave", back_populates="channel")

    __table_args__ = {"comment": "通道表"}

    def to_dict(self) -> ChannelDict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    def is_tcp(self) -> bool:
        """是否为 TCP 连接"""
        return self.conn_type in [1, 2]

    def is_serial(self) -> bool:
        """是否为串口连接"""
        return self.conn_type == 0
