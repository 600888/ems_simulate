"""按 IEC 61850 通道持久化的 GOOSE 接收与订阅配置。"""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.data.model.base import Base


class GooseReceiverConfig(Base):
    __tablename__ = "goose_receiver"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("channel.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, server_default="default")
    description: Mapped[str] = mapped_column(String(512), nullable=False, server_default="")
    interface: Mapped[str] = mapped_column(String(256), nullable=False)
    auto_start: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")

    subscriptions: Mapped[list["GooseSubscriptionConfig"]] = relationship(
        back_populates="receiver", cascade="all, delete-orphan", order_by="GooseSubscriptionConfig.id"
    )

    __table_args__ = (
        UniqueConstraint("channel_id", "interface", "name", name="uq_goose_receiver_channel_interface_name"),
        {"comment": "GOOSE 接收器配置"},
    )


class GooseSubscriptionConfig(Base):
    __tablename__ = "goose_subscription"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    receiver_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("goose_receiver.id", ondelete="CASCADE"), nullable=False, index=True
    )
    go_cb_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    app_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dst_mac_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(String(512), nullable=False, server_default="")
    data_set_ref: Mapped[str] = mapped_column(String(256), nullable=False, server_default="")
    conf_rev: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    ied_name: Mapped[str] = mapped_column(String(128), nullable=False, server_default="")
    ld_inst: Mapped[str] = mapped_column(String(128), nullable=False, server_default="")
    ln_name: Mapped[str] = mapped_column(String(128), nullable=False, server_default="LLN0")
    dataset_entries_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    go_id: Mapped[str] = mapped_column(String(256), nullable=False, server_default="")

    receiver: Mapped[GooseReceiverConfig] = relationship(back_populates="subscriptions")

    __table_args__ = (
        UniqueConstraint("receiver_id", "go_cb_ref", "app_id", name="uq_goose_subscription_filter"),
        {"comment": "GOOSE 订阅配置"},
    )
