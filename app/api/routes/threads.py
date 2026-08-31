"""Thread listing and deletion, backed by the LangGraph checkpointer."""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import CurrentUser
from app.logging import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/v1/threads", tags=["threads"])


def _checkpointer(request: Request):
    cp = getattr(request.app.state, "checkpointer", None)
    if cp is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "checkpointer unavailable")
    return cp


@router.get("")
async def list_threads(principal: CurrentUser, cp=Depends(_checkpointer)) -> dict:
    threads = []
    async for state in cp.alist({"configurable": {}}, limit=100):
        values = state.checkpoint.get("channel_values", {})
        if values.get("user_id") != principal.user_id:
            continue
        messages = values.get("messages") or []
        preview = ""
        for m in messages:
            content = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else "")
            if content:
                preview = str(content)[:120]
                break
        threads.append(
            {
                "thread_id": state.config["configurable"]["thread_id"],
                "preview": preview,
                "updated_at": state.metadata.get("ts"),
            }
        )
    return {"threads": threads}


@router.get("/{thread_id}")
async def get_thread(thread_id: str, principal: CurrentUser, cp=Depends(_checkpointer)) -> dict:
    state = await cp.aget({"configurable": {"thread_id": thread_id}})
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thread not found")

    values = state.get("channel_values", {})
    if values.get("user_id") != principal.user_id:
        # 404 rather than 403 — don't confirm the thread exists.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thread not found")

    messages = [
        {
            "role": getattr(m, "type", "message"),
            "content": str(getattr(m, "content", "")),
        }
        for m in values.get("messages", [])
    ]
    return {"thread_id": thread_id, "messages": messages}


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_thread(thread_id: str, principal: CurrentUser, cp=Depends(_checkpointer)) -> None:
    state = await cp.aget({"configurable": {"thread_id": thread_id}})
    if state is None:
        return
    if state.get("channel_values", {}).get("user_id") != principal.user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "thread not found")
    await cp.adelete_thread(thread_id)
    log.info("thread_deleted", user_id=principal.user_id)
