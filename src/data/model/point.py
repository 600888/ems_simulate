from typing import TypedDict
from sqlalchemy import Integer, String, Boolean, Float
from sqlalchemy.orm import mapped_column, Mapped

from src.data.model.base import Base


class ModbusPointDict(TypedDict):
    id: int
    no: int
    grp_code: str
    rtu_addr: str
    reg_addr: str
    bit: int
    func_code: str
    decode_code: str
    frame_type: int
    code: str
    desc: str
    save_interval: int
    mul_coe: float
    add_coe: float
    max_limit: float
    min_limit: float
    ctrl_type: int
    event_level: int
    alarm_type: int
    reverse: int
    src_grp_code: str
    src_no: int


class ModbusPoint(Base):
    __tablename__ = "modbus_point"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, nullable=False, comment="id"
    )
    no: Mapped[int] = mapped_column(Integer, comment="测点编号")
    grp_code: Mapped[str] = mapped_column(String(32), comment="组编码")
    rtu_addr: Mapped[str] = mapped_column(String(32), comment="远端地址")
    reg_addr: Mapped[str] = mapped_column(String(32), comment="寄存器地址")
    bit: Mapped[int] = mapped_column(
        Integer, nullable=True, comment="位,只有遥信数据才有"
    )
    func_code: Mapped[str] = mapped_column(
        String(10), server_default="", comment="功能码"
    )
    decode_code: Mapped[str] = mapped_column(
        String(10), server_default="", comment="解析码"
    )
    frame_type: Mapped[int] = mapped_column(
        Integer, comment="帧类型，0：遥测帧，1：遥信帧，2：遥控帧，3：遥调帧"
    )
    code: Mapped[str] = mapped_column(String(64), comment="测点描述编码")
    desc: Mapped[str] = mapped_column(String(64), comment="测点描述")
    save_interval: Mapped[int] = mapped_column(
        Integer, server_default="0", comment="保存间隔"
    )
    mul_coe: Mapped[float] = mapped_column(
        Float, server_default="1.0", comment="乘系数"
    )
    add_coe: Mapped[float] = mapped_column(
        Float, server_default="0.0", comment="加系数"
    )
    max_limit: Mapped[float] = mapped_column(
        Float, server_default="9999999", comment="上限值"
    )
    min_limit: Mapped[float] = mapped_column(
        Float, server_default="-9999999", comment="下限值"
    )
    ctrl_type: Mapped[int] = mapped_column(
        Integer, server_default="0", comment="控制类型"
    )
    is_alarm: Mapped[bool] = mapped_column(
        Boolean, server_default="0", comment="是否产生告警"
    )
    event_level: Mapped[int] = mapped_column(
        Integer, server_default="0", comment="事件等级，0代表不告警，1-4逐级增大"
    )
    alarm_type: Mapped[int] = mapped_column(
        Integer,
        server_default="0",
        comment="报警类型，0:无报警，1:提示告警，2:次要告警，3:重要告警，4:紧急告警",
    )
    reverse: Mapped[bool] = mapped_column(
        Boolean, server_default="0", comment="是否反转"
    )
    # src_grp_code: Mapped[str] = mapped_column(
    #     String(64), server_default="", comment="源组编码"
    # )
    # src_no: Mapped[int] = mapped_column(Integer, server_default="-1", comment="源编号")
    __table_args__ = {"comment": "modbus测点表"}

    def to_dict(self) -> ModbusPointDict:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
