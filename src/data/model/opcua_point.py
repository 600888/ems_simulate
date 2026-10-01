"""Imported OPC UA point metadata, independent of the legacy four-point tables."""

from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.data.model.base import Base


class OpcUaPoint(Base):
    __tablename__ = "opcua_point"
    __table_args__ = (
        UniqueConstraint("channel_id", "point_code", name="uq_opcua_point_code"),
        UniqueConstraint("channel_id", "node_id", name="uq_opcua_point_node_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channel.id"), nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    point_type: Mapped[int] = mapped_column(Integer, nullable=False)
    point_code: Mapped[str] = mapped_column(String(128), nullable=False)
    point_name: Mapped[str] = mapped_column(String(255), nullable=False)
    attribute_code: Mapped[str] = mapped_column(String(255), nullable=False)
    node_id: Mapped[str] = mapped_column(String(512), nullable=False)
    namespace_uri: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sampling_interval_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scale_mul: Mapped[float | None] = mapped_column(Float, nullable=True)
    scale_add: Mapped[float | None] = mapped_column(Float, nullable=True)
    upper_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    lower_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    initial_value: Mapped[Any] = mapped_column(JSON, nullable=False)
    reverse: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    command_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    related_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
