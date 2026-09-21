"""v0.1.2.4 Defect 3/Phase 7: the report's main EVIDENCE section must
contain admitted evidence only. Before this fix, app/orchestration/
executor.py::build_report only ever excluded evidence with
relevance_label == "REJECT" — an off-topic item that the OLDER relevance
scoring alone scored MEDIUM (not REJECT) still reached evidence_details.
This is the exact bug the checkpoint flagged: "the current report says
one additional rejected item was excluded while obviously unrelated HR
evidence still appears in the admitted list." Offline — mirrors
tests/test_report_open_questions_cleanup.py's style.
"""
from __future__ import annotations


async def test_admission_rejected_evidence_excluded_even_when_relevance_label_is_not_reject(session_factory):
    from app.database.models import TaskStatus
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("admissionreport@example.com")
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
                        "id": "e-relevant",
                        "claim": "Legitimate business finding about the candidate's pricing.",
                        "source_url": "https://gumroad.com/l/x",
                        "relevance_label": "HIGH",
                        "admission_status": "ACCEPTED",
                    },
                    {
                        # The exact leak this fix closes: MEDIUM relevance
                        # (not REJECT), but caught by the admission gate's
                        # candidate-overlap rule — a wrong-market
                        # authoritative source.
                        "id": "e-hr-medium-relevance",
                        "claim": "Candidate skills assessment market size report.",
                        "source_url": "https://www.grandviewresearch.com/candidate-assessment-market",
                        "relevance_label": "MEDIUM",
                        "admission_status": "REJECTED",
                        "admission_rejection_reasons": ["INSUFFICIENT_CANDIDATE_OVERLAP"],
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
    assert "e-hr-medium-relevance" not in evidence_ids_shown
    assert report.rejected_evidence_count == 1
    assert report.rejected_evidence_reasons.get("INSUFFICIENT_CANDIDATE_OVERLAP") == 1
    text = report.to_text()
    assert "REJECTED / OFF-TOPIC EVIDENCE: 1 item(s) excluded" in text
    assert "INSUFFICIENT_CANDIDATE_OVERLAP" in text
    assert "candidate skills assessment" not in text.lower()
