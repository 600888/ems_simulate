"""Protected secrets are separate from ordinary configuration and API output."""

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.data.model.base import Base


class OpcUaSecret(Base):
    __tablename__ = "opcua_secret"
    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channel.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
