from typing import TypedDict
from sqlalchemy import Integer, String, Boolean, UniqueConstraint
from sqlalchemy.orm import mapped_column, Mapped
from src.data.model.base import Base


class YxDict(TypedDict):
    id: int
    no: int
    code: str
    name: str
    reg_addr: str
    bit: int
    grp_code: str
    src_grp_code: str
    src_no: int
    is_alarm: bool
    event_level: int
    alarm_type: int
    reverse: int
    ctrl_type: int
    valid_state: int


# 遥信 数据表
class Yx(Base):
    __tablename__ = "yx"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="遥信id")
    no: Mapped[int] = mapped_column(Integer, nullable=False, comment="遥信编号")
    code: Mapped[str] = mapped_column(String(64), nullable=False, comment="遥信编码")
    name: Mapped[str] = mapped_column(String(64), comment="遥信名称")
    reg_addr: Mapped[str] = mapped_column(String(32), comment="遥信寄存器地址")
    bit: Mapped[int] = mapped_column(Integer, comment="遥信位")
    grp_code: Mapped[str] = mapped_column(String(64), nullable=False, comment="组编码")
    src_grp_code: Mapped[str] = mapped_column(
        String(64), server_default="", comment="源组编码"
    )
    src_no: Mapped[int] = mapped_column(Integer, server_default="-1", comment="源编号")
    is_alarm: Mapped[bool] = mapped_column(
        Boolean, server_default="0", comment="是否报警"
    )
    event_level: Mapped[int] = mapped_column(
        Integer, server_default="0", comment="事件类型"
    )
    alarm_type: Mapped[int] = mapped_column(
        Integer,
        comment="报警类型, 0:无报警, 1:提示告警, 2:次要告警, 3:重要告警, 4:紧急告警",
    )
    reverse: Mapped[int] = mapped_column(Integer, comment="反转")
    ctrl_type: Mapped[int] = mapped_column(Integer, comment="控制类型")
    valid_state: Mapped[int] = mapped_column(
        Boolean, server_default="0", comment="正常值"
    )

    __table_args__ = (
        UniqueConstraint("code", "grp_code", name="uq_yx"),
        {"comment": "遥信数据表"},
    )

    def to_dict(self) -> YxDict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
