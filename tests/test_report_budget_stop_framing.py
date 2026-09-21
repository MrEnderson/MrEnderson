"""Phase 13 (v0.1.2.2): a token/API-call safety-limit stop must never
automatically suggest raising the limit — it's a feature, not an
obstacle. Offline — mirrors tests/test_report_lifecycle.py's style."""
from __future__ import annotations


async def test_token_budget_stop_does_not_recommend_raising_the_limit(session_factory):
    from app.database.models import TaskStatus
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("budgetstop@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        ts = TaskService(session)
        strategy_task = await ts.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Strategy", agent_type="strategy"
        )
        await session.commit()
        workspace_id, project_id, strategy_id = workspace.id, project.id, strategy_task.id

    async with session_factory() as session:
        ts = TaskService(session)
        await ts.transition(strategy_id, TaskStatus.READY, workspace_id=workspace_id)
        await ts.transition(strategy_id, TaskStatus.RUNNING, workspace_id=workspace_id)
        await ts.transition(
            strategy_id,
            TaskStatus.COMPLETED,
            workspace_id=workspace_id,
            output_data={
                "options_considered": [],
                "recommendation": (
                    "DECISION STATUS: INSUFFICIENT COMPARABLE EVIDENCE\n"
                    "MOST PROMISING VALIDATION CANDIDATE: X (provisional)\n"
                    "MISSING INFORMATION: Y: pricing\n"
                    "NEXT VALIDATION: Run targeted follow-up research."
                ),
                "reasoning": "r", "assumptions": ["a"], "evidence_used": [], "unsupported_claims": [],
                "confidence": 0.3, "comparison_ready": False,
                "candidate_statuses": [], "missing_requirements": ["Y: pricing"], "remediation_queries": [],
                # Per the QA readiness contract (Phase 10), a correct refusal
                # under comparison_ready=false PASSES QA — PASS means
                # "correctly handled insufficient evidence," not "business
                # opportunity validated."
                "qa_verdict": "PASS", "qa_score": 0.8, "qa_feedback": "Correct handling of insufficient evidence.",
            },
        )
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj",
            budget_stopped_reason="MAX_TOKENS_PER_MISSION (200000) reached",
        )

    assert report.status == "STOPPED_BUDGET_LIMIT"
    assert not any("raise the limit" in a.lower() for a in report.next_actions)
    assert any("safety limit" in a.lower() for a in report.next_actions)
    assert any("bounded mission" in a.lower() or "new bounded" in a.lower() for a in report.next_actions)

    # 25. Provisional/not-yet-validated language survives into the report.
    assert report.recommendation.startswith("DECISION STATUS: INSUFFICIENT COMPARABLE EVIDENCE")
    text = report.to_text()
    assert "DECISION STATUS: INSUFFICIENT COMPARABLE EVIDENCE" in text
    assert "RECOMMENDATION: DECISION STATUS" not in text


async def test_cost_based_budget_stop_still_suggests_raising_the_limit(session_factory):
    """Only the TOKEN/API-call safety limit gets the "feature, not an
    obstacle" framing — a cost-based limit is a different axis and keeps
    the existing framing."""
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("costlimit@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        await session.commit()
        workspace_id, project_id = workspace.id, project.id

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj",
            budget_stopped_reason="MAX_ESTIMATED_COST_PER_MISSION_USD ($5.0) reached",
        )

    assert any("raise the limit" in a.lower() for a in report.next_actions)
