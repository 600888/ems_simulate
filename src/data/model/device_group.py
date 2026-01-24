"""
设备组表模型
管理设备组层级结构，支持多层嵌套
"""

from typing import TypedDict, Optional, List
from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import mapped_column, Mapped, relationship

from src.data.model.base import Base


class DeviceGroupDict(TypedDict):
    """设备组字典类型"""
    id: int
    code: str
    name: str
    parent_id: Optional[int]
    description: Optional[str]
    status: int
    enable: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class DeviceGroup(Base):
    """设备组表 - 支持多层嵌套层级结构"""
    __tablename__ = "device_group"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="设备组ID"
    )
    code: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True, comment="设备组编码"
    )
    name: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="设备组名称"
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("device_group.id"), nullable=True, index=True, 
        comment="父设备组ID（用于多层嵌套）"
    )
    description: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True, comment="设备组描述"
    )
    status: Mapped[int] = mapped_column(
        Integer, server_default="0", 
        comment="设备组状态: 0:正常, 1:告警, 2:故障, 3:离线"
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

    # 关系 - 父子设备组层级（自引用）
    parent = relationship("DeviceGroup", back_populates="children", remote_side=[id])
    children: Mapped[List["DeviceGroup"]] = relationship(
        "DeviceGroup", back_populates="parent", cascade="all, delete-orphan"
    )
    
    # 关系 - 组内设备
    devices = relationship("Device", back_populates="group")

    __table_args__ = {"comment": "设备组表"}

    def to_dict(self) -> DeviceGroupDict:
        """转换为字典"""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
    
    def to_tree_dict(self, include_devices: bool = True) -> dict:
        """转换为树形结构字典（包含子设备组和设备）
        
        Args:
            include_devices: 是否包含组内设备列表
        """
        result = self.to_dict()
        # 递归获取子设备组
        result["children"] = [
            child.to_tree_dict(include_devices) 
            for child in self.children 
            if child.enable
        ]
        # 包含组内设备
        if include_devices:
            result["devices"] = [
                device.to_dict() 
                for device in self.devices 
                if device.enable
            ]
        return result
