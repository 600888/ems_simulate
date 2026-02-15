"""
测点映射模型
用于存储测点之间的计算关系
"""

from typing import TypedDict, Optional, List
from sqlalchemy import Integer, String, Boolean, Text, UniqueConstraint
from sqlalchemy.orm import mapped_column, Mapped

from src.data.model.base import Base


class PointMappingDict(TypedDict):
    """测点映射字典类型"""
    id: int
    device_name: str
    target_point_code: str
    source_point_codes: str  # JSON list of codes
    formula: str
    enable: bool


class PointMapping(Base):
    """测点映射表"""
    __tablename__ = "point_mapping"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="映射ID"
    )
    device_name: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="设备名称"
    )
    target_point_code: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="目标测点编码"
    )
    source_point_codes: Mapped[str] = mapped_column(
        Text, nullable=False, comment="源测点编码列表(JSON)"
    )
    formula: Mapped[str] = mapped_column(
        Text, nullable=False, comment="计算公式"
    )
    enable: Mapped[bool] = mapped_column(
        Boolean, server_default="1", comment="是否启用"
    )

    __table_args__ = (
        UniqueConstraint('device_name', 'target_point_code', name='uix_device_target_point'),
        {"comment": "测点映射表"},
    )

    def to_dict(self) -> PointMappingDict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
