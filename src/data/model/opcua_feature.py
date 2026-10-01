"""Versioned desired feature configuration; never UA runtime identifiers."""

from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.data.model.base import Base


class OpcUaFeature(Base):
    __tablename__ = "opcua_feature"

    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channel.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
