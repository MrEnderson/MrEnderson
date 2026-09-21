"""v0.1.2.6 Phase 9: report section semantics. OPEN QUESTIONS used to
mix actual questions, unresolved evidence gaps, QA feedback, and
unsupported-claim warnings into one list. Split into four distinct report
concepts. Offline — mirrors tests/test_report_open_questions_cleanup.py's
style."""
from __future__ import annotations


async def test_unresolved_evidence_gaps_kept_separate_from_open_questions(session_factory):
    from app.database.models import TaskStatus
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("gaps-section@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        ts = TaskService(session)
        task = await ts.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Validate candidates", agent_type="research"
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
                "question": "q", "findings": [], "assumptions": [],
                "unsupported_claims": ["Revenue is likely $5M without a cited source."],
                "open_questions": ["Is there a viable distribution channel for this candidate?"],
                "evidence_gaps": [
                    {
                        "id": "g1", "gap_type": "pricing", "candidate_id": "candidate-a",
                        "claim_or_question": "Missing pricing evidence for Candidate A", "resolved": False,
                    }
                ],
                "insufficient_evidence": True, "summary": "s", "evidence": [],
            },
        )
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj"
        )

    # Actual business question stays in OPEN QUESTIONS.
    assert any("viable distribution channel" in q for q in report.open_questions)
    assert not any("pricing" in q.lower() for q in report.open_questions)
    assert not any("Revenue is likely" in q for q in report.open_questions)

    # The gap moved to its own structured section.
    assert any("candidate-a" in g and "pricing" in g for g in report.unresolved_evidence_gaps)

    # The unsupported claim moved to its own section.
    assert any("Revenue is likely" in c for c in report.unsupported_claims)

    text = report.to_text()
    assert "UNRESOLVED EVIDENCE GAPS:" in text
    assert "UNSUPPORTED CLAIMS:" in text


async def test_qa_notes_bounded_and_distinct_from_open_questions(session_factory):
    from app.database.models import TaskStatus
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("qa-notes-section@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        ts = TaskService(session)
        task = await ts.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Validate candidates", agent_type="research"
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
                "question": "q", "findings": [], "assumptions": [], "unsupported_claims": [],
                "open_questions": [], "evidence_gaps": [], "insufficient_evidence": False, "summary": "s",
                "evidence": [], "qa_verdict": "NEEDS_REVIEW", "qa_score": 0.4,
                "qa_feedback": "Needs more independent sources for pricing." * 3,
            },
        )
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj"
        )

    assert report.qa_notes
    assert all(len(n) < 400 for n in report.qa_notes)
    assert report.open_questions == []
    text = report.to_text()
    assert "QA NOTES:" in text
