"""
遥信测点表模型 (Yx)
frame_type = 1
"""

from typing import TypedDict

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.data.model.base import Base


class PointYxDict(TypedDict):
    """遥信点字典类型"""

    id: int
    code: str
    name: str
    channel_id: int | None
    rtu_addr: int
    reg_addr: str
    func_code: int
    decode_code: str
    bit: int | None
    reverse: bool
    # IEC104 特定字段
    iec_common_address: int | None
    iec_cot: int | None
    iec_quality: int | None
    iec_type_id: str | None
    fc: str | None
    enable: bool


class PointYx(Base):
    """遥信测点表"""

    __tablename__ = "point_yx"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="测点ID")
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="测点编码")
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="测点名称")
    channel_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("channel.id"), nullable=True, index=True, comment="所属通道ID"
    )
    rtu_addr: Mapped[int] = mapped_column(Integer, server_default="1", comment="从机地址/IEC104信息对象地址")
    reg_addr: Mapped[str] = mapped_column(String(128), nullable=False, comment="寄存器地址")
    func_code: Mapped[int] = mapped_column(Integer, server_default="1", comment="功能码")
    decode_code: Mapped[str] = mapped_column(String(10), server_default="0x20", comment="解析码(Modbus专用)")

    # 遥信特有字段
    bit: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="位偏移")
    reverse: Mapped[bool] = mapped_column(Boolean, server_default="0", comment="是否反转")

    # IEC104 特定字段
    iec_common_address: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="IEC104公共地址")
    iec_cot: Mapped[int | None] = mapped_column(
        Integer, nullable=True, server_default="3", comment="IEC104传送原因(COT)"
    )
    iec_quality: Mapped[int | None] = mapped_column(
        Integer, nullable=True, server_default="0", comment="IEC104品质描述符(位标志: BL=0x02 SB=0x04 NT=0x08 IV=0x10)"
    )
    iec_type_id: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="IEC104类型标识(如M_SP_NA_1)")

    # IEC61850 特定字段
    fc: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="IEC61850功能约束(FC), 如MX/ST/CO/DC/CF/SF等"
    )
    dnp3_config: Mapped[str | None] = mapped_column(Text, nullable=True, comment="DNP3点级配置(JSON)")

    enable: Mapped[bool] = mapped_column(Boolean, server_default="1", comment="是否启用")

    __table_args__ = (
        UniqueConstraint("code", "channel_id", "rtu_addr", name="uq_point_yx_code_channel_rtu"),
        {"comment": "遥信测点表"},
    )

    @property
    def frame_type(self) -> int:
        return 1

    def to_dict(self) -> PointYxDict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
