"""Memory tool — permission-checked interface onto MemoryService."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import AgentRegistry
from app.database.models import Memory, MemoryType, PermissionLevel
from app.security.permissions import check_permission
from app.services.memory_service import MemoryService


async def store_memory(
    session: AsyncSession,
    registry: AgentRegistry,
    *,
    acting_agent_type: str,
    workspace_id: str,
    type: MemoryType,
    title: str,
    content: str,
    source: str | None = None,
    importance: int = 3,
) -> Memory:
    check_permission(registry, acting_agent_type, PermissionLevel.WRITE)
    return await MemoryService(session).store(
        workspace_id=workspace_id,
        type=type,
        title=title,
        content=content,
        source=source,
        importance=importance,
    )


async def retrieve_memory(
    session: AsyncSession,
    registry: AgentRegistry,
    *,
    acting_agent_type: str,
    workspace_id: str,
    type: MemoryType | None = None,
    keyword: str | None = None,
    min_importance: int | None = None,
) -> list[Memory]:
    check_permission(registry, acting_agent_type, PermissionLevel.READ)
    return await MemoryService(session).retrieve(
        workspace_id=workspace_id, type=type, keyword=keyword, min_importance=min_importance
    )
