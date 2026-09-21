"""Executive report changes for incomplete research (Phase 13). Offline —
mirrors the style of tests/test_report_lifecycle.py."""
from __future__ import annotations


async def test_report_shows_not_yet_validated_framing_when_comparison_not_ready(session_factory):
    from app.database.models import TaskStatus
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("ri@example.com")
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
                    "MOST PROMISING VALIDATION CANDIDATE: Notion template marketplace (provisional)\n"
                    "MISSING INFORMATION: Coda template hub: demand\n"
                    "NEXT VALIDATION: Run targeted follow-up research."
                ),
                "reasoning": "r",
                "assumptions": ["a"],
                "evidence_used": [],
                "unsupported_claims": [],
                "confidence": 0.3,
                "comparison_ready": False,
                "candidate_statuses": [
                    {
                        "candidate_id": "notion-template-marketplace",
                        "candidate_label": "Notion template marketplace",
                        "coverage_percentage": 1.0,
                        "critical_requirements_missing": [],
                        "other_material_gaps": [],
                        "ready_for_comparison": True,
                    },
                    {
                        "candidate_id": "coda-template-hub",
                        "candidate_label": "Coda template hub",
                        "coverage_percentage": 0.0,
                        "critical_requirements_missing": ["demand", "competition", "pricing"],
                        "other_material_gaps": [],
                        "ready_for_comparison": False,
                    },
                ],
                "missing_requirements": ["Coda template hub: demand"],
                "remediation_queries": ["Coda template hub demand"],
                "qa_verdict": "NEEDS_REVIEW",
                "qa_score": 0.4,
                "qa_feedback": "Comparison not ready.",
            },
        )
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj"
        )

    assert report.comparison_ready is False
    assert any("Coda template hub" in line for line in report.evidence_coverage)
    assert any("demand" in g.lower() for g in report.critical_gaps)
    assert report.next_research == ["Coda template hub demand"]
    assert report.recommendation.startswith("DECISION STATUS: INSUFFICIENT COMPARABLE EVIDENCE")

    text = report.to_text()
    # Never headlined with a generic "RECOMMENDATION:" prefix in front of an
    # already-qualified DECISION STATUS framing.
    assert "RECOMMENDATION: DECISION STATUS" not in text
    assert "DECISION STATUS: INSUFFICIENT COMPARABLE EVIDENCE" in text
    assert "COMPARISON READINESS: NOT READY" in text
    assert "EVIDENCE COVERAGE:" in text
    assert "CRITICAL GAPS:" in text
    assert "NEXT RESEARCH:" in text


async def test_report_shows_normal_recommendation_when_comparison_ready_and_qa_pass(session_factory):
    from app.database.models import TaskStatus
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("ready@example.com")
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
                "recommendation": "Pursue the Notion template marketplace opportunity.",
                "reasoning": "r",
                "assumptions": ["a"],
                "evidence_used": [],
                "unsupported_claims": [],
                "confidence": 0.8,
                "comparison_ready": True,
                "candidate_statuses": [],
                "missing_requirements": [],
                "remediation_queries": [],
                "qa_verdict": "PASS",
                "qa_score": 0.9,
                "qa_feedback": "fine",
            },
        )
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj"
        )

    assert report.comparison_ready is True
    assert report.recommendation == "Pursue the Notion template marketplace opportunity."
    text = report.to_text()
    assert "RECOMMENDATION: Pursue the Notion template marketplace opportunity." in text
    assert "COMPARISON READINESS: READY" in text
