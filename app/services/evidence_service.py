"""Evidence persistence. Stores exactly what ResearchAgent retrieved — never
called with model-invented data (see app/agents/research.py)."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Evidence
from app.database.repositories import EvidenceRepository
from app.schemas.evidence import EvidenceItem
from app.security.audit import AuditEventType, record_event


class EvidenceService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.evidence = EvidenceRepository(session)

    async def store_many(
        self, *, workspace_id: str, project_id: str, task_id: str, items: list[EvidenceItem]
    ) -> list[Evidence]:
        if not items:
            return []

        stored = [
            await self.evidence.create(
                evidence_id=item.id,
                workspace_id=workspace_id,
                project_id=project_id,
                task_id=task_id,
                claim=item.claim,
                source_title=item.source_title,
                source_url=item.source_url,
                publisher=item.publisher,
                published_at=item.published_at,
                retrieved_at=item.retrieved_at,
                excerpt=item.excerpt,
                evidence_type=item.evidence_type,
                confidence=item.confidence,
                query_used=item.query_used,
                verification_status=item.verification_status,
                source_quality=item.source_quality,
                evidence_depth=item.evidence_depth,
            )
            for item in items
        ]

        await record_event(
            self.session,
            workspace_id=workspace_id,
            actor_type="research",
            event_type=AuditEventType.EVIDENCE_STORED,
            entity_type="task",
            entity_id=task_id,
            metadata={"count": len(stored), "project_id": project_id},
        )
        return stored

    async def list_for_project(self, project_id: str) -> list[Evidence]:
        return await self.evidence.list_for_project(project_id)
