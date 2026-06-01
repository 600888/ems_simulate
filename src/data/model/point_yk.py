"""
遥控测点表模型 (Yk)
frame_type = 2
"""

from typing import TypedDict

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.data.model.base import Base


class PointYkDict(TypedDict):
    """遥控点字典类型"""

    id: int
    code: str
    name: str
    channel_id: int | None
    rtu_addr: int
    reg_addr: str
    func_code: int
    decode_code: str
    bit: int | None
    command_type: int
    related_yx_id: int | None
    # IEC104 特定字段
    iec_common_address: int | None
    iec_cot: int | None
    iec_quality: int | None
    iec_type_id: str | None
    fc: str | None
    enable: bool


class PointYk(Base):
    """遥控测点表"""

    __tablename__ = "point_yk"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="测点ID")
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="测点编码")
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="测点名称")
    channel_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("channel.id"), nullable=True, index=True, comment="所属通道ID"
    )
    rtu_addr: Mapped[int] = mapped_column(Integer, server_default="1", comment="从机地址/IEC104信息对象地址")
    reg_addr: Mapped[str] = mapped_column(String(128), nullable=False, comment="寄存器地址")
    func_code: Mapped[int] = mapped_column(Integer, server_default="5", comment="功能码")
    decode_code: Mapped[str] = mapped_column(String(10), server_default="0x20", comment="解析码(Modbus专用)")

    # 遥控特有字段
    bit: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="位偏移")
    command_type: Mapped[int] = mapped_column(Integer, server_default="0", comment="命令类型: 0:单点, 1:双点")
    related_yx_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("point_yx.id"), nullable=True, comment="关联遥信点ID"
    )

    # IEC104 特定字段
    iec_common_address: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="IEC104公共地址")
    iec_cot: Mapped[int | None] = mapped_column(
        Integer, nullable=True, server_default="3", comment="IEC104传送原因(COT)"
    )
    iec_quality: Mapped[int | None] = mapped_column(
        Integer, nullable=True, server_default="0", comment="IEC104品质描述符(遥控方向通常不带品质)"
    )
    iec_type_id: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="IEC104类型标识(如C_SC_NA_1)")

    # IEC61850 特定字段
    fc: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="IEC61850功能约束(FC), 如MX/ST/CO/DC/CF/SF等"
    )

    enable: Mapped[bool] = mapped_column(Boolean, server_default="1", comment="是否启用")

    __table_args__ = (
        UniqueConstraint("code", "channel_id", "rtu_addr", name="uq_point_yk_code_channel_rtu"),
        {"comment": "遥控测点表"},
    )

    @property
    def frame_type(self) -> int:
        return 2

    def to_dict(self) -> PointYkDict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
