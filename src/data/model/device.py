"""
设备表模型
管理设备基本信息
"""

from datetime import datetime
from typing import TypedDict

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.data.model.base import Base


class DeviceDict(TypedDict):
    """设备字典类型"""

    id: int
    code: str
    name: str
    device_type: int
    group_id: int | None
    enable: bool
    created_at: datetime | None
    updated_at: datetime | None
    # IEC 61850 ICD 文件关联
    icd_path: str | None
    icd_file_hash: str | None


class Device(Base):
    """设备表"""

    __tablename__ = "device"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="设备ID")
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True, comment="设备编码")
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="设备名称")
    device_type: Mapped[int] = mapped_column(
        Integer,
        server_default="0",
        comment="设备类型: 0:其他, 1:PCS, 2:BMS, 3:空调, 4:电表, 5:消防",
    )
    group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("device_group.id"), nullable=True, index=True, comment="所属设备组ID（NULL表示未分组）"
    )
    enable: Mapped[bool] = mapped_column(Boolean, server_default="1", comment="是否启用")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    # 关系 - 通道
    channels = relationship("Channel", back_populates="device")

    # 关系 - 所属设备组
    group = relationship("DeviceGroup", back_populates="devices")

    # IEC 61850 ICD 文件关联
    icd_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="ICD文件存储路径 (IEC61850)")
    icd_file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="ICD文件内容Hash (IEC61850)")

    __table_args__ = {"comment": "设备表"}

    def to_dict(self) -> DeviceDict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
