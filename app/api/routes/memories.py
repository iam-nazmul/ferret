"""Long-term memory: view and delete."""

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, get_store
from app.api.schemas import MemoryItem
from app.logging import get_logger
from app.memory.store import delete_all_memories, delete_memory, list_memories

log = get_logger(__name__)
router = APIRouter(prefix="/v1/memories", tags=["memories"])


@router.get("", response_model=list[MemoryItem])
async def get_memories(principal: CurrentUser, store=Depends(get_store)) -> list[MemoryItem]:
    if store is None:
        return []
    items = await list_memories(store, principal.user_id)
    return [MemoryItem(**i) for i in items]


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_memory(memory_id: str, principal: CurrentUser, store=Depends(get_store)) -> None:
    if store is not None:
        await delete_memory(store, principal.user_id, memory_id)


@router.delete("", status_code=status.HTTP_200_OK)
async def clear_memories(principal: CurrentUser, store=Depends(get_store)) -> dict:
    if store is None:
        return {"deleted": 0}
    count = await delete_all_memories(store, principal.user_id)
    log.info("memories_cleared", user_id=principal.user_id, count=count)
    return {"deleted": count}
