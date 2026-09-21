"""Memory service. Only intentionally-promoted knowledge is stored long-term —
callers must explicitly decide something is worth remembering; nothing here
auto-saves raw conversation turns."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Memory, MemoryType
from app.database.repositories import MemoryRepository
from app.security.audit import AuditEventType, record_event


class MemoryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.memories = MemoryRepository(session)

    async def store(
        self,
        *,
        workspace_id: str,
        type: MemoryType,
        title: str,
        content: str,
        source: str | None = None,
        importance: int = 3,
    ) -> Memory:
        memory = await self.memories.create(
            workspace_id=workspace_id,
            type=type,
            title=title,
            content=content,
            source=source,
            importance=importance,
        )
        await record_event(
            self.session,
            workspace_id=workspace_id,
            actor_type="jarvis",
            event_type=AuditEventType.MEMORY_CREATED,
            entity_type="memory",
            entity_id=memory.id,
            metadata={"type": type.value, "title": title},
        )
        return memory

    async def retrieve(
        self,
        *,
        workspace_id: str,
        type: MemoryType | None = None,
        keyword: str | None = None,
        min_importance: int | None = None,
    ) -> list[Memory]:
        return await self.memories.search(
            workspace_id=workspace_id, type=type, keyword=keyword, min_importance=min_importance
        )
