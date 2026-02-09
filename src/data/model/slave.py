"""
从机表模型 (Slave)
管理通道下的从机配置
"""

from typing import TypedDict, Optional
from sqlalchemy import Integer, String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import mapped_column, Mapped, relationship

from src.data.model.base import Base


class SlaveDict(TypedDict):
    """从机字典类型"""
    id: int
    channel_id: int
    slave_id: int
    name: Optional[str]
    enable: bool


class Slave(Base):
    """从机表 - 管理通道下的从机配置"""
    __tablename__ = "slave"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="主键ID"
    )
    channel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("channel.id"), nullable=False, index=True, comment="所属通道ID"
    )
    slave_id: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="从机地址(0-247)"
    )
    name: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, comment="从机名称"
    )
    enable: Mapped[bool] = mapped_column(
        Boolean, server_default="1", comment="是否启用"
    )

    # 关系
    channel = relationship("Channel", back_populates="slaves")

    __table_args__ = (
        UniqueConstraint("channel_id", "slave_id", name="uq_slave_channel_slave"),
        {"comment": "从机表"}
    )

    def to_dict(self) -> SlaveDict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
