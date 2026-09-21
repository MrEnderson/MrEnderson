"""Memory creation and retrieval by workspace/type/keyword/importance."""
from __future__ import annotations

from app.database.models import MemoryType
from app.database.repositories import UserRepository, WorkspaceRepository
from app.memory.retrieval import retrieve_relevant
from app.services.memory_service import MemoryService


async def _make_workspace(session):
    user = await UserRepository(session).get_or_create_by_email("m@example.com")
    workspace = await WorkspaceRepository(session).create(user.id, "Memory Workspace")
    await session.commit()
    return workspace.id


async def test_store_and_retrieve_memory(session):
    workspace_id = await _make_workspace(session)
    service = MemoryService(session)

    await service.store(
        workspace_id=workspace_id,
        type=MemoryType.DECISION,
        title="Chose coloring books",
        content="Decided to pursue the coloring-book niche.",
        importance=5,
    )
    await service.store(
        workspace_id=workspace_id,
        type=MemoryType.RESEARCH,
        title="Market scan",
        content="General market notes.",
        importance=2,
    )
    await session.commit()

    decisions = await service.retrieve(workspace_id=workspace_id, type=MemoryType.DECISION)
    assert len(decisions) == 1
    assert decisions[0].title == "Chose coloring books"

    by_keyword = await service.retrieve(workspace_id=workspace_id, keyword="coloring")
    assert len(by_keyword) == 1

    important_only = await service.retrieve(workspace_id=workspace_id, min_importance=4)
    assert len(important_only) == 1


async def test_retrieve_relevant_orders_by_importance(session):
    workspace_id = await _make_workspace(session)
    service = MemoryService(session)
    await service.store(
        workspace_id=workspace_id, type=MemoryType.FACT, title="Low", content="x", importance=1
    )
    await service.store(
        workspace_id=workspace_id, type=MemoryType.FACT, title="High", content="y", importance=5
    )
    await session.commit()

    ranked = await retrieve_relevant(session, workspace_id=workspace_id, top_k=2)
    assert ranked[0].title == "High"


async def test_memory_is_scoped_to_workspace(session):
    workspace_a = await _make_workspace(session)
    user_b = await UserRepository(session).get_or_create_by_email("other@example.com")
    workspace_b = await WorkspaceRepository(session).create(user_b.id, "Other Workspace")
    await session.commit()

    service = MemoryService(session)
    await service.store(
        workspace_id=workspace_a,
        type=MemoryType.FACT,
        title="A-only",
        content="belongs to workspace A",
    )
    await session.commit()

    results = await service.retrieve(workspace_id=workspace_b.id)
    assert results == []
