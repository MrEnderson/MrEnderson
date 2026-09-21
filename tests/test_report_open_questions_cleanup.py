"""v0.1.2.3 "Report cleanup": OPEN QUESTIONS holds actual questions/gaps,
not an entire raw multi-paragraph QA essay, and REJECT-relevance evidence
is summarized as rejected rather than mixed into business findings.
Offline — mirrors tests/test_report_lifecycle.py's style."""
from __future__ import annotations


async def test_open_questions_does_not_contain_raw_multi_paragraph_qa_feedback(session_factory):
    from app.database.models import TaskStatus
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    long_feedback = (
        "The Strategy output correctly identifies that comparison is not yet possible given "
        "incomplete evidence across the three candidates. However, several additional concerns "
        "should be raised: the pricing evidence for candidate B relies on a single source, the "
        "competitive analysis for candidate C lacks named competitors, the market size claims "
        "throughout are backed only by discovery-tier sources, and the customer pain evidence "
        "for all three candidates is thin. " * 3
    )
    assert len(long_feedback) > 400  # confirm the fixture is actually long

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("openq@example.com")
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
                "options_considered": [], "recommendation": "DECISION STATUS: INSUFFICIENT COMPARABLE EVIDENCE",
                "reasoning": "r", "assumptions": ["a"], "evidence_used": [], "unsupported_claims": [],
                "confidence": 0.3, "comparison_ready": False,
                "candidate_statuses": [], "missing_requirements": [], "remediation_queries": [],
                "qa_verdict": "NEEDS_REVIEW", "qa_score": 0.4, "qa_feedback": long_feedback,
            },
        )
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj"
        )

    # v0.1.2.6 Phase 9: QA observations are their own report section
    # (qa_notes), never mixed into OPEN QUESTIONS.
    assert report.qa_notes
    for line in report.qa_notes:
        assert len(line) < 400  # bounded, never the raw ~700+ char essay
    assert not any(long_feedback in q for q in report.qa_notes)
    assert not any("flagged" in q.lower() for q in report.open_questions)


async def test_rejected_evidence_summarized_not_mixed_into_evidence_details(session_factory):
    from app.database.models import TaskStatus
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("rejectedev@example.com")
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
                "evidence": [
                    {
                        "id": "e-relevant", "claim": "Legitimate business finding about the candidate's pricing.",
                        "source_url": "https://gumroad.com/l/x", "relevance_label": "HIGH",
                    },
                    {
                        "id": "e-hr-noise",
                        "claim": "Candidate screening, background checks, and ATS recruiting tools overview.",
                        "source_url": "https://random-hr-blog.example.com/ats",
                        "relevance_label": "REJECT", "rejection_reason": "IRRELEVANT_TOPIC",
                    },
                ],
            },
        )
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj"
        )

    evidence_ids_shown = {e.id for e in report.evidence_details}
    assert "e-relevant" in evidence_ids_shown
    assert "e-hr-noise" not in evidence_ids_shown
    assert report.rejected_evidence_count == 1
    assert "REJECTED / OFF-TOPIC EVIDENCE: 1 item(s) excluded" in report.to_text()
