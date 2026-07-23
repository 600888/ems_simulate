"""IEC 61850 可编辑模型工程的持久化实体。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from src.data.model.base import Base


class Iec61850ModelProject(Base):
    """一个可独立编辑、校验和发布的 IEC 61850 模型工程。"""

    __tablename__ = "iec61850_model_project"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    file_type: Mapped[str] = mapped_column(String(16), nullable=False, default="ICD")
    standard_version: Mapped[str] = mapped_column(String(32), nullable=False, default="IEC 61850 Ed2.1")
    namespace: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    modeling_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="FROM_SCRATCH")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT", index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    validation_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_warnings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_json: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"), nullable=False, default="{}")
    model_format_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    model_node_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_checksum: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Iec61850ModelVersion(Base):
    """模型工程的完整版本快照。"""

    __tablename__ = "iec61850_model_version"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("iec61850_model_project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="SNAPSHOT", index=True)
    source_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("project_id", "version_number", name="uq_iec61850_model_version_number"),)
