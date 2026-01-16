from typing import TypedDict
from sqlalchemy import Integer, String, Float, UniqueConstraint
from sqlalchemy.orm import mapped_column, Mapped

from src.data.model.base import Base


class YcDict(TypedDict):
    id: int
    no: int
    code: str
    name: str
    grp_code: str
    src_grp_code: str
    src_no: int
    event_level: int
    mul_coe: float
    add_coe: float
    save_interval: int
    max_limit: float
    min_limit: float
    ctrl_type: int


# 遥测 数据表
class Yc(Base):
    __tablename__ = "yc"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, comment="遥测id")
    no: Mapped[int] = mapped_column(Integer, nullable=False, comment="遥测编号")
    code: Mapped[str] = mapped_column(String(64), nullable=False, comment="遥测编码")
    name: Mapped[str] = mapped_column(String(64), comment="遥测名称")
    grp_code: Mapped[str] = mapped_column(String(64), nullable=False, comment="组编码")
    src_grp_code: Mapped[str] = mapped_column(
        String(64), server_default="", comment="源组编码"
    )
    src_no: Mapped[int] = mapped_column(Integer, server_default="-1", comment="源编号")
    event_level: Mapped[int] = mapped_column(
        Integer, server_default="0", comment="事件等级, 0代表不告警, 1-4逐级增大"
    )
    mul_coe: Mapped[float] = mapped_column(Float, server_default="1", comment="乘系数")
    add_coe: Mapped[float] = mapped_column(Float, server_default="0", comment="加系数")
    save_interval: Mapped[int] = mapped_column(Integer, comment="保存间隔")
    max_limit: Mapped[float] = mapped_column(
        Float, server_default="9999999", comment="上限值"
    )
    min_limit: Mapped[float] = mapped_column(
        Float, server_default="-9999999", comment="下限值"
    )
    ctrl_type: Mapped[int] = mapped_column(Integer, comment="控制类型")

    __table_args__ = (
        UniqueConstraint("code", "grp_code", name="uq_yc"),
        {"comment": "遥测数据表"},
    )

    def to_dict(self) -> YcDict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
