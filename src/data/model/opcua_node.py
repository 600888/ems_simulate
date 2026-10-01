"""M1 OPC UA variable definitions, separate from the four legacy point tables."""

from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.data.model.base import Base


class OpcUaNode(Base):
    __tablename__ = "opcua_node"
    __table_args__ = (UniqueConstraint("channel_id", "node_id", name="uq_opcua_node_channel_node_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channel.id"), nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    namespace_uri: Mapped[str] = mapped_column(String(255), nullable=False)
    node_id: Mapped[str] = mapped_column(String(512), nullable=False)
    browse_name: Mapped[str] = mapped_column(String(128), nullable=False)
    data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    initial_value: Mapped[Any] = mapped_column(JSON, nullable=False)
    writable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
