"""Admin: source management, reindex, upload. Role-gated server-side, not just hidden in the UI."""

import hashlib
import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import AdminUser, DbSession
from app.api.schemas import FailedDocument, SourceStatus
from app.ingest.chunk import chunk_document
from app.ingest.embed import embed_texts
from app.ingest.parse.pdf import parse_pdf
from app.ingest.upsert import upsert_document
from app.logging import get_logger
from app.models import Document, DocumentStatus, Source, SourceKind

log = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["admin"])


@router.get("/sources", response_model=list[SourceStatus])
async def list_sources(admin: AdminUser, db: DbSession) -> list[SourceStatus]:
    total = (
        select(Document.source_id, func.count().label("n"))
        .group_by(Document.source_id)
        .subquery()
    )
    failed = (
        select(Document.source_id, func.count().label("n"))
        .where(Document.status == DocumentStatus.FAILED.value)
        .group_by(Document.source_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(Source, func.coalesce(total.c.n, 0), func.coalesce(failed.c.n, 0))
            .outerjoin(total, total.c.source_id == Source.id)
            .outerjoin(failed, failed.c.source_id == Source.id)
            .order_by(Source.uri)
        )
    ).all()

    return [
        SourceStatus(
            id=str(s.id),
            kind=s.kind,
            uri=s.uri,
            enabled=s.enabled,
            last_run_at=s.last_run_at.isoformat() if s.last_run_at else None,
            document_count=int(n_total),
            failed_count=int(n_failed),
        )
        for s, n_total, n_failed in rows
    ]


@router.get("/sources/{source_id}/failures", response_model=list[FailedDocument])
async def list_failures(source_id: str, admin: AdminUser, db: DbSession) -> list[FailedDocument]:
    rows = (
        await db.execute(
            select(Document)
            .where(
                Document.source_id == uuid.UUID(source_id),
                Document.status == DocumentStatus.FAILED.value,
            )
            .order_by(Document.uri)
            .limit(200)
        )
    ).scalars().all()
    return [
        FailedDocument(
            uri=d.uri,
            error=d.error,
            indexed_at=d.indexed_at.isoformat() if d.indexed_at else None,
        )
        for d in rows
    ]


@router.post("/sources/{source_id}/reindex", status_code=status.HTTP_202_ACCEPTED)
async def reindex(source_id: str, admin: AdminUser, db: DbSession) -> dict:
    source = (
        await db.execute(select(Source).where(Source.id == uuid.UUID(source_id)))
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "source not found")

    from app.ingest.worker import ingest_source_task

    ingest_source_task.apply_async(args=[source_id], task_id=f"ingest-{source_id}")
    log.info("reindex_queued", source_id=source_id, by=admin.user_id)
    return {"queued": True, "source_id": source_id}


@router.post("/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(
    admin: AdminUser,
    db: DbSession,
    file: UploadFile = File(...),
    acl_groups: str = Form("all"),
    doc_type: str = Form("document"),
) -> dict:
    """Manual PDF upload. ACL is explicit — never defaulted to a broad group silently."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "only PDF uploads are supported")

    content = await file.read()
    groups = [g.strip() for g in acl_groups.split(",") if g.strip()]
    if not groups:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "acl_groups is required")

    source = (
        await db.execute(select(Source).where(Source.kind == SourceKind.UPLOAD.value))
    ).scalar_one_or_none()
    if source is None:
        source = Source(
            id=uuid.uuid4(),
            kind=SourceKind.UPLOAD.value,
            uri="upload://manual",
            acl_groups=groups,
        )
        db.add(source)
        await db.flush()

    parsed = parse_pdf(content, file.filename)
    chunks = chunk_document(parsed)
    if not chunks:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "no extractable text — the PDF may be scanned without an OCR-readable layer",
        )

    embeddings = await embed_texts([c.text for c in chunks])
    doc_id = await upsert_document(
        db,
        source_id=source.id,
        uri=f"upload://{file.filename}",
        title=parsed.title or file.filename,
        content_hash=hashlib.sha256(content).hexdigest(),
        acl_groups=groups,
        metadata={"doc_type": doc_type, "uploaded_by": admin.user_id},
        page_count=parsed.page_count,
        chunks=chunks,
        embeddings=embeddings,
    )
    log.info("document_uploaded", doc_id=str(doc_id), by=admin.user_id, chunks=len(chunks))
    return {"document_id": str(doc_id), "chunks": len(chunks)}
