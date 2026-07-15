"""IEC 61850 可编辑模型工程的持久化实体。"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
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
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Iec61850ModelNode(Base):
    """通用模型节点；不同节点的业务字段保存在 attributes_json 中。"""

    __tablename__ = "iec61850_model_node"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("iec61850_model_project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("iec61850_model_node.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attributes_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("project_id", "parent_id", "kind", "name", name="uq_iec61850_model_sibling"),)


class Iec61850ModelReference(Base):
    """节点间显式引用，用于删除影响分析和后续 FCDA/类型引用。"""

    __tablename__ = "iec61850_model_reference"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("iec61850_model_project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("iec61850_model_node.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_node_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("iec61850_model_node.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    attributes_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
