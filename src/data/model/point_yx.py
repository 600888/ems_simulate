"""
遥信测点表模型 (Yx)
frame_type = 1
"""

from typing import TypedDict, Optional
from sqlalchemy import Integer, String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import mapped_column, Mapped

from src.data.model.base import Base


class PointYxDict(TypedDict):
    """遥信点字典类型"""
    id: int
    code: str
    name: str
    channel_id: Optional[int]
    rtu_addr: int
    reg_addr: str
    func_code: int
    decode_code: str
    bit: Optional[int]
    reverse: bool
    # IEC104 特定字段
    iec_common_address: Optional[int]
    iec_cot: Optional[int]
    iec_quality: Optional[int]
    enable: bool


class PointYx(Base):
    """遥信测点表"""
    __tablename__ = "point_yx"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="测点ID"
    )
    code: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="测点编码"
    )
    name: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="测点名称"
    )
    channel_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("channel.id"), nullable=True, index=True, comment="所属通道ID"
    )
    rtu_addr: Mapped[int] = mapped_column(
        Integer, server_default="1", comment="从机地址/IEC104信息对象地址"
    )
    reg_addr: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="寄存器地址"
    )
    func_code: Mapped[int] = mapped_column(
        Integer, server_default="1", comment="功能码"
    )
    decode_code: Mapped[str] = mapped_column(
        String(10), server_default="0x20", comment="解析码(Modbus专用)"
    )

    # 遥信特有字段
    bit: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="位偏移"
    )
    reverse: Mapped[bool] = mapped_column(
        Boolean, server_default="0", comment="是否反转"
    )
    
    # IEC104 特定字段
    iec_common_address: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="IEC104公共地址"
    )
    iec_cot: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default="3", comment="IEC104传送原因(COT)"
    )
    iec_quality: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default="0", comment="IEC104品质描述符"
    )

    enable: Mapped[bool] = mapped_column(
        Boolean, server_default="1", comment="是否启用"
    )

    __table_args__ = (
        UniqueConstraint("code", "channel_id", "rtu_addr", name="uq_point_yx_code_channel_rtu"),
        {"comment": "遥信测点表"}
    )

    @property
    def frame_type(self) -> int:
        return 1

    def to_dict(self) -> PointYxDict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
