"""Executive report: human-readable evidence rendering, the stale
"Connect a live ResearchProvider" next-action fix, and per-provider/model
usage breakdown with initial-vs-retry visibility. Offline only."""
from __future__ import annotations

from app.schemas.evidence import EvidenceItem
from app.schemas.reports import AgentUsageBreakdown, ExecutiveReport, MissionUsage


def _report(**overrides) -> ExecutiveReport:
    base = dict(objective="obj", status="COMPLETED", recommendation="Do X")
    base.update(overrides)
    return ExecutiveReport(**base)


# --- Human-readable evidence rendering --------------------------------------


def test_evidence_details_render_claim_source_url_not_just_uuid():
    item = EvidenceItem(
        claim="The micro-SaaS market is growing.",
        source_title="Micro-SaaS Report 2026",
        source_url="https://example.com/report",
        publisher="example.com",
    )
    report = _report(evidence_details=[item])
    text = report.to_text()

    assert "Claim: The micro-SaaS market is growing." in text
    assert "Source: Micro-SaaS Report 2026" in text
    assert "URL: https://example.com/report" in text
    assert "Publisher/domain: example.com" in text
    assert f"(id: {item.id})" in text


def test_report_with_evidence_details_is_not_uuid_only():
    item = EvidenceItem(claim="claim text", source_url="https://example.com/x")
    report = _report(evidence_details=[item])
    text = report.to_text()
    # The UUID must appear, but only as a parenthetical, never as the heading.
    assert f"[1] Claim:" in text
    assert f"[1] {item.id}" not in text


def test_missing_metadata_shown_honestly_not_fabricated():
    item = EvidenceItem(claim="claim with no known publisher", source_url=None)
    report = _report(evidence_details=[item])
    text = report.to_text()
    assert "Publisher/domain: unknown" in text
    assert "URL: unknown" in text


def test_falls_back_to_plain_list_when_no_evidence_details():
    report = _report(evidence=["free text evidence note"], evidence_details=[])
    text = report.to_text()
    assert "free text evidence note" in text
    assert "EVIDENCE:" in text


def test_empty_evidence_shows_none():
    report = _report()
    assert "EVIDENCE:\n  (none)" in report.to_text()


# --- Stale "Connect a live ResearchProvider" next-action fix ----------------


async def test_next_action_absent_when_live_evidence_was_collected(session_factory):
    from app.database.models import TaskStatus
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.schemas.evidence import EvidenceItem
    from app.services.evidence_service import EvidenceService
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("r@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        task_service = TaskService(session)
        task = await task_service.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Research X", agent_type="research"
        )
        await session.commit()
        workspace_id, project_id, task_id = workspace.id, project.id, task.id

    async with session_factory() as session:
        ts = TaskService(session)
        # Evidence must be persisted through EvidenceService, exactly as
        # AgentExecutor does — that's the source of truth build_report()
        # checks (research_evidence_present), not the task's own output_data.
        item = EvidenceItem(id="ev-1", claim="c", source_url="https://example.com/a")
        await EvidenceService(session).store_many(
            workspace_id=workspace_id, project_id=project_id, task_id=task_id, items=[item]
        )
        await ts.transition(task_id, TaskStatus.READY, workspace_id=workspace_id)
        await ts.transition(task_id, TaskStatus.RUNNING, workspace_id=workspace_id)
        await ts.transition(
            task_id,
            TaskStatus.COMPLETED,
            workspace_id=workspace_id,
            output_data={
                "question": "X",
                "findings": [],
                "evidence": [item.model_dump(mode="json")],
                "assumptions": [],
                "unsupported_claims": [],
                "open_questions": [],
                "evidence_gaps": [],
                "insufficient_evidence": False,
                "summary": "s",
            },
        )
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj"
        )
    assert not any("Connect a live ResearchProvider" in a for a in report.next_actions)


async def test_followup_research_action_appears_when_evidence_still_insufficient(session_factory):
    from app.database.models import TaskStatus
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.schemas.evidence import EvidenceItem
    from app.services.evidence_service import EvidenceService
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("r2@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        ts = TaskService(session)
        task = await ts.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Research X", agent_type="research"
        )
        await session.commit()
        workspace_id, project_id, task_id = workspace.id, project.id, task.id

    async with session_factory() as session:
        ts = TaskService(session)
        item = EvidenceItem(id="ev-1", claim="c", source_url="https://example.com/a")
        await EvidenceService(session).store_many(
            workspace_id=workspace_id, project_id=project_id, task_id=task_id, items=[item]
        )
        await ts.transition(task_id, TaskStatus.READY, workspace_id=workspace_id)
        await ts.transition(task_id, TaskStatus.RUNNING, workspace_id=workspace_id)
        await ts.transition(
            task_id,
            TaskStatus.COMPLETED,
            workspace_id=workspace_id,
            output_data={
                "question": "X",
                "findings": [],
                "evidence": [item.model_dump(mode="json")],
                "assumptions": [],
                "unsupported_claims": [],
                "open_questions": [],
                "evidence_gaps": [],
                "insufficient_evidence": True,  # still insufficient, despite real evidence existing
                "summary": "s",
            },
        )
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj"
        )
    assert any("follow-up research" in a.lower() for a in report.next_actions)
    assert not any("Connect a live ResearchProvider" in a for a in report.next_actions)


async def test_next_action_present_for_pure_dev_mode_no_evidence(session_factory):
    from app.database.models import TaskStatus
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("r3@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        ts = TaskService(session)
        task = await ts.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Research X", agent_type="research"
        )
        await session.commit()
        workspace_id, project_id, task_id = workspace.id, project.id, task.id

    async with session_factory() as session:
        ts = TaskService(session)
        await ts.transition(task_id, TaskStatus.READY, workspace_id=workspace_id)
        await ts.transition(task_id, TaskStatus.RUNNING, workspace_id=workspace_id)
        await ts.transition(
            task_id,
            TaskStatus.COMPLETED,
            workspace_id=workspace_id,
            output_data={
                "question": "X",
                "findings": [],
                "evidence": [],
                "assumptions": [],
                "unsupported_claims": [],
                "open_questions": [],
                "evidence_gaps": [],
                "insufficient_evidence": True,
                "summary": "no live provider connected",
            },
        )
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj"
        )
    assert any("Connect a live ResearchProvider" in a for a in report.next_actions)


# --- Usage breakdown: provider/model + initial vs retry ---------------------


def test_usage_section_shows_provider_model_and_initial_retry_split():
    usage = MissionUsage(
        by_agent=[
            AgentUsageBreakdown(
                agent_type="research", provider="anthropic", model="claude-haiku-4-5-20251001",
                api_calls=3, initial_calls=1, retry_calls=2, input_tokens=100, output_tokens=50, total_tokens=150,
            ),
            AgentUsageBreakdown(
                agent_type="research", provider="tavily", model="search",
                api_calls=5, initial_calls=1, retry_calls=4,
            ),
        ],
        total_api_calls=8, total_retries=6,
    )
    report = _report(usage=usage)
    text = report.to_text()
    assert "Research (anthropic/claude-haiku-4-5-20251001): 3 calls (initial 1, retries 2)" in text
    assert "Research (tavily/search): 5 calls (initial 1, retries 4)" in text
