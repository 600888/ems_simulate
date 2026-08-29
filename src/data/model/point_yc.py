"""
遥测测点表模型 (Yc)
frame_type = 0
"""

from typing import TypedDict

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.data.model.base import Base


class PointYcDict(TypedDict):
    """遥测点字典类型"""

    id: int
    code: str
    name: str
    channel_id: int | None
    rtu_addr: int
    reg_addr: str
    func_code: int
    decode_code: str
    mul_coe: float
    add_coe: float
    max_limit: float
    min_limit: float
    # IEC104 特定字段
    iec_common_address: int | None
    iec_cot: int | None
    iec_quality: int | None
    iec_type_id: str | None
    fc: str | None
    enable: bool


class PointYc(Base):
    """遥测测点表"""

    __tablename__ = "point_yc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="测点ID")
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="测点编码")
    name: Mapped[str] = mapped_column(String(64), nullable=False, comment="测点名称")
    channel_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("channel.id"), nullable=True, index=True, comment="所属通道ID"
    )
    rtu_addr: Mapped[int] = mapped_column(Integer, server_default="1", comment="从机地址/IEC104信息对象地址")
    reg_addr: Mapped[str] = mapped_column(String(128), nullable=False, comment="寄存器地址")
    func_code: Mapped[int] = mapped_column(Integer, server_default="3", comment="功能码")
    decode_code: Mapped[str] = mapped_column(String(10), server_default="0x41", comment="解析码(Modbus专用)")

    # 遥测特有字段
    mul_coe: Mapped[float] = mapped_column(Float, server_default="1.0", comment="乘系数")
    add_coe: Mapped[float] = mapped_column(Float, server_default="0.0", comment="加系数")
    max_limit: Mapped[float] = mapped_column(Float, comment="上限值")
    min_limit: Mapped[float] = mapped_column(Float, comment="下限值")

    # IEC104 特定字段
    iec_common_address: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="IEC104公共地址")
    iec_cot: Mapped[int | None] = mapped_column(
        Integer, nullable=True, server_default="3", comment="IEC104传送原因(COT)"
    )
    iec_quality: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        server_default="0",
        comment="IEC104品质描述符(位标志: OV BL SB NT IV)",
    )
    iec_type_id: Mapped[str | None] = mapped_column(String(16), nullable=True, comment="IEC104类型标识(如M_ME_NC_1)")

    # IEC61850 特定字段
    fc: Mapped[str | None] = mapped_column(
        String(8), nullable=True, comment="IEC61850功能约束(FC), 如MX/ST/CO/DC/CF/SF等"
    )
    dnp3_config: Mapped[str | None] = mapped_column(Text, nullable=True, comment="DNP3点级配置(JSON)")

    enable: Mapped[bool] = mapped_column(Boolean, server_default="1", comment="是否启用")

    __table_args__ = (
        UniqueConstraint("code", "channel_id", "rtu_addr", name="uq_point_yc_code_channel_rtu"),
        {"comment": "遥测测点表"},
    )

    @property
    def frame_type(self) -> int:
        return 0

    def to_dict(self) -> PointYcDict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
