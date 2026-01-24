"""
设备表模型
管理设备基本信息
"""

from typing import TypedDict, Optional
from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import mapped_column, Mapped, relationship

from src.data.model.base import Base


class DeviceDict(TypedDict):
    """设备字典类型"""
    id: int
    code: str
    name: str
    device_type: int
    group_id: Optional[int]
    enable: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class Device(Base):
    """设备表"""
    __tablename__ = "device"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="设备ID"
    )
    code: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True, comment="设备编码"
    )
    name: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="设备名称"
    )
    device_type: Mapped[int] = mapped_column(
        Integer,
        server_default="0",
        comment="设备类型: 0:其他, 1:PCS, 2:BMS, 3:空调, 4:电表, 5:消防",
    )
    group_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("device_group.id"), nullable=True, index=True,
        comment="所属设备组ID（NULL表示未分组）"
    )
    enable: Mapped[bool] = mapped_column(
        Boolean, server_default="1", comment="是否启用"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    # 关系 - 通道
    channels = relationship("Channel", back_populates="device")
    
    # 关系 - 所属设备组
    group = relationship("DeviceGroup", back_populates="devices")

    __table_args__ = {"comment": "设备表"}

    def to_dict(self) -> DeviceDict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

