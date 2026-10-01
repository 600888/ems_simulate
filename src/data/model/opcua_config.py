"""Dedicated OPC UA endpoint configuration without credentials or private keys."""

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.data.model.base import Base


class OpcUaConfig(Base):
    __tablename__ = "opcua_config"

    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channel.id"), primary_key=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    endpoint_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    endpoint_path: Mapped[str] = mapped_column(String(255), nullable=False, default="/ems/")
    namespace_uri: Mapped[str | None] = mapped_column(String(255), nullable=True)
