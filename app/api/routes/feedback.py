"""Feedback: stored locally and forwarded to LangSmith."""

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.api.schemas import FeedbackRequest
from app.config import settings
from app.logging import get_logger
from app.models import Feedback

log = get_logger(__name__)
router = APIRouter(prefix="/v1/feedback", tags=["feedback"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def submit_feedback(body: FeedbackRequest, principal: CurrentUser, db: DbSession) -> dict:
    row = Feedback(
        id=uuid.uuid4(),
        run_id=uuid.UUID(body.run_id),
        thread_id=body.thread_id,
        user_id=principal.user_id,
        score=body.score,
        comment=body.comment,
    )
    db.add(row)
    await db.commit()

    if settings.langsmith_api_key:
        try:
            from langsmith import Client

            Client().create_feedback(
                body.run_id,
                key="user_thumb",
                score=body.score,
                comment=body.comment,
            )
        except Exception as exc:
            # Local record is the source of truth; LangSmith is best-effort.
            log.warning("langsmith_feedback_failed", error=str(exc))

    log.info("feedback_recorded", score=body.score, user_id=principal.user_id)
    return {"id": str(row.id)}
