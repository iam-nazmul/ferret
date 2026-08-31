import enum
import uuid
from datetime import datetime

from sqlalchemy import ARRAY, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class DocumentStatus(enum.StrEnum):
    PENDING = "pending"
    INDEXED = "indexed"
    FAILED = "failed"
    STALE = "stale"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("source_id", "uri", name="uq_documents_source_uri"),
        Index("ix_documents_acl_groups", "acl_groups", postgresql_using="gin"),
        Index("ix_documents_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
    )
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acl_groups: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    doc_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=DocumentStatus.PENDING)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    source = relationship("Source", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
