import enum
import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class SourceKind(enum.StrEnum):
    PDF_BUCKET = "pdf_bucket"
    WEB_SITEMAP = "web_sitemap"
    UPLOAD = "upload"


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    crawl_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    acl_groups: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    documents = relationship("Document", back_populates="source", cascade="all, delete-orphan")
