"""
GOOSE Publisher 数据库模型

存储 GOOSE Publisher 的配置和数据集条目，实现持久化。
"""

from typing import Any, TypedDict

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.data.model.base import Base


class GooseEntryDict(TypedDict):
    """GOOSE 数据集条目字典类型"""

    id: int
    publisher_id: int
    name: str
    value: Any | None
    iec_type: str
    sort_order: int


class GoosePublisherDict(TypedDict):
    """GOOSE Publisher 字典类型"""

    id: int
    channel_id: int | None
    interface: str
    go_cb_ref: str
    go_id: str
    data_set_ref: str
    app_id: int
    conf_rev: int
    time_allowed_to_live: int
    dst_mac_list: list[int] | None
    vlan_id: int
    vlan_prio: int
    simulation: bool
    name: str
    description: str
    auto_start: bool
    entries: list[GooseEntryDict]


class GooseEntry(Base):
    """GOOSE 数据集条目表"""

    __tablename__ = "goose_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="条目ID")
    publisher_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("goose_publisher.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属 Publisher ID",
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False, comment="条目名称 (FCDA 引用路径)")
    value: Mapped[str | None] = mapped_column(Text, nullable=True, comment="默认值 (JSON 序列化)")
    iec_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="boolean", comment="IEC 数据类型")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="排序序号")

    publisher: Mapped["GoosePublisher"] = relationship(back_populates="entries")

    def to_dict(self) -> GooseEntryDict:
        return {
            "id": self.id,
            "publisher_id": self.publisher_id,
            "name": self.name,
            "value": self._parse_value(),
            "iec_type": self.iec_type,
            "sort_order": self.sort_order,
        }

    def _parse_value(self) -> Any:
        """将 JSON 字符串解析回原始 Python 值"""
        if self.value is None:
            return None
        import json

        try:
            return json.loads(self.value)
        except (json.JSONDecodeError, TypeError):
            return self.value


class GoosePublisher(Base):
    """GOOSE Publisher 配置表"""

    __tablename__ = "goose_publisher"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="Publisher ID")
    channel_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("channel.id"), nullable=True, index=True, comment="所属通道ID"
    )
    interface: Mapped[str] = mapped_column(String(64), nullable=False, server_default="eth0", comment="网络接口")
    go_cb_ref: Mapped[str] = mapped_column(String(256), nullable=False, index=True, comment="GOOSE 控制块引用")
    go_id: Mapped[str] = mapped_column(String(128), nullable=False, server_default="", comment="GOOSE 标识符")
    data_set_ref: Mapped[str] = mapped_column(String(256), nullable=False, server_default="", comment="数据集引用")
    app_id: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", comment="APPID")
    conf_rev: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1", comment="配置修订号")
    time_allowed_to_live: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="1000", comment="存活时间 (ms)"
    )
    dst_mac_json: Mapped[str | None] = mapped_column(Text, nullable=True, comment="目标 MAC 地址 (JSON 数组)")
    vlan_id: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", comment="VLAN ID")
    vlan_prio: Mapped[int] = mapped_column(Integer, nullable=False, server_default="4", comment="VLAN 优先级")
    simulation: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1", comment="仿真模式")
    name: Mapped[str] = mapped_column(String(128), nullable=False, server_default="", comment="显示名称")
    description: Mapped[str] = mapped_column(String(512), nullable=False, server_default="", comment="描述")
    auto_start: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0", comment="自动启动")

    # 关系
    entries: Mapped[list["GooseEntry"]] = relationship(
        back_populates="publisher",
        cascade="all, delete-orphan",
        order_by="GooseEntry.sort_order",
    )

    __table_args__ = (
        UniqueConstraint("channel_id", "go_cb_ref", name="uq_goose_publisher_channel_gocb"),
        {"comment": "GOOSE 发布配置"},
    )

    def to_dict(self) -> GoosePublisherDict:
        return {
            "id": self.id,
            "channel_id": self.channel_id,
            "interface": self.interface,
            "go_cb_ref": self.go_cb_ref,
            "go_id": self.go_id,
            "data_set_ref": self.data_set_ref,
            "app_id": self.app_id,
            "conf_rev": self.conf_rev,
            "time_allowed_to_live": self.time_allowed_to_live,
            "dst_mac_list": self._parse_dst_mac(),
            "vlan_id": self.vlan_id,
            "vlan_prio": self.vlan_prio,
            "simulation": self.simulation,
            "name": self.name,
            "description": self.description,
            "auto_start": self.auto_start,
            "entries": [e.to_dict() for e in self.entries],
        }

    def _parse_dst_mac(self) -> list[int] | None:
        """将 JSON 字符串解析为 MAC 地址列表"""
        if not self.dst_mac_json:
            return None
        import json

        try:
            return json.loads(self.dst_mac_json)
        except (json.JSONDecodeError, TypeError):
            return None
