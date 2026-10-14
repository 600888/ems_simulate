"""DL/T 698 definitions stay outside the legacy floating point point tables."""

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.data.model.base import Base


class Dlt698Point(Base):
    __tablename__ = "dlt698_point"
    __table_args__ = (UniqueConstraint("channel_id", "code", name="uq_dlt698_channel_code"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channel.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(128))
    definition: Mapped[dict] = mapped_column(JSON)
