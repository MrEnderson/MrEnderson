"""Long-term memory retrieval. Deliberately simple keyword/type/importance matching
for v0.1 — see the module docstring's note in docs/architecture.md for how a
vector store would slot in later behind the same `retrieve_relevant` signature."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Memory, MemoryType
from app.services.memory_service import MemoryService


async def retrieve_relevant(
    session: AsyncSession,
    *,
    workspace_id: str,
    keyword: str | None = None,
    type: MemoryType | None = None,
    top_k: int = 5,
) -> list[Memory]:
    memories = await MemoryService(session).retrieve(
        workspace_id=workspace_id, type=type, keyword=keyword
    )
    ranked = sorted(memories, key=lambda m: (m.importance, m.created_at), reverse=True)
    return ranked[:top_k]
