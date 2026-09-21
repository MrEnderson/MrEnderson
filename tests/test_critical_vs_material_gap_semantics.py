"""v0.1.2.4 Defect 4: CRITICAL GAPS (demand/competition/pricing fully
MISSING) vs. OTHER MATERIAL GAPS (everything else not SUFFICIENT — a
non-critical category fully MISSING, or a critical category sitting at
WEAK/PARTIAL rather than fully MISSING). Before this fix, both of those
"everything else" cases were silently dropped from the report — never in
critical_requirements_missing (not critical, or not fully MISSING) and
never in the old weak_requirements (only caught WEAK/PARTIAL, never
MISSING). Offline — no network call.
"""
from __future__ import annotations

from app.config.settings import get_settings
from app.research_intelligence.completeness import evaluate_completeness
from app.research_intelligence.schemas import CoverageCell


def _cell(candidate_id: str, category: str, status: str, requirement_id: str | None = None) -> CoverageCell:
    return CoverageCell(
        requirement_id=requirement_id or f"{candidate_id}-{category}",
        candidate_id=candidate_id,
        category=category,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
    )


def test_noncritical_category_fully_missing_is_not_silently_dropped():
    """feasibility is NOT a critical category (CRITICAL_CATEGORIES =
    demand/competition/pricing) — before the fix, a fully-MISSING
    feasibility cell appeared in neither list. Now: other_material_gaps."""
    settings = get_settings()
    cells = [
        _cell("c1", "demand", "SUFFICIENT"),
        _cell("c1", "competition", "SUFFICIENT"),
        _cell("c1", "pricing", "MISSING"),
        _cell("c1", "customer_pain", "SUFFICIENT"),
        _cell("c1", "market_size", "MISSING"),
        _cell("c1", "feasibility", "MISSING"),
    ]
    readiness = evaluate_completeness(
        requirements=[], coverage_cells=cells, candidate_labels={"c1": "Candidate One"}, settings=settings
    )
    status = readiness.candidate_statuses[0]
    assert status.critical_requirements_missing == ["pricing"]
    assert "market_size" in status.other_material_gaps
    assert "feasibility" in status.other_material_gaps
    assert "pricing" not in status.other_material_gaps  # already counted as critical, not duplicated


def test_critical_category_weak_not_fully_missing_is_other_material_not_dropped():
    """demand/competition are critical categories, but WEAK/PARTIAL (some
    evidence, just not enough) — never fully MISSING. Before the fix these
    were caught by the old `weak_requirements` list; the renamed field must
    keep catching them."""
    settings = get_settings()
    cells = [
        _cell("c1", "demand", "WEAK"),
        _cell("c1", "competition", "PARTIAL"),
        _cell("c1", "pricing", "MISSING"),
        _cell("c1", "customer_pain", "SUFFICIENT"),
        _cell("c1", "market_size", "SUFFICIENT"),
        _cell("c1", "feasibility", "SUFFICIENT"),
    ]
    readiness = evaluate_completeness(
        requirements=[], coverage_cells=cells, candidate_labels={"c1": "Candidate One"}, settings=settings
    )
    status = readiness.candidate_statuses[0]
    assert status.critical_requirements_missing == ["pricing"]
    assert set(status.other_material_gaps) == {"demand", "competition"}


def test_every_non_sufficient_cell_appears_in_exactly_one_list():
    """Invariant: nothing is ever silently dropped — every non-SUFFICIENT
    cell is in critical_requirements_missing XOR other_material_gaps."""
    settings = get_settings()
    cells = [
        _cell("c1", "demand", "MISSING"),
        _cell("c1", "competition", "WEAK"),
        _cell("c1", "pricing", "SUFFICIENT"),
        _cell("c1", "customer_pain", "PARTIAL"),
        _cell("c1", "market_size", "MISSING"),
        _cell("c1", "feasibility", "SUFFICIENT"),
    ]
    readiness = evaluate_completeness(
        requirements=[], coverage_cells=cells, candidate_labels={"c1": "Candidate One"}, settings=settings
    )
    status = readiness.candidate_statuses[0]
    non_sufficient = {c.category for c in cells if c.status != "SUFFICIENT"}
    accounted = set(status.critical_requirements_missing) | set(status.other_material_gaps)
    assert non_sufficient == accounted
    assert not (set(status.critical_requirements_missing) & set(status.other_material_gaps))


async def test_report_shows_other_material_gaps_distinct_from_critical_gaps(session_factory):
    """End-to-end through build_report + ExecutiveReport.to_text(): CRITICAL
    GAPS and OTHER MATERIAL GAPS render as separate, clearly-labeled
    sections, matching the checkpoint's requested example format."""
    from app.database.models import TaskStatus
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("gaps@example.com")
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
                "recommendation": "DECISION STATUS: INSUFFICIENT COMPARABLE EVIDENCE",
                "reasoning": "r",
                "assumptions": [],
                "evidence_used": [],
                "unsupported_claims": [],
                "confidence": 0.3,
                "comparison_ready": False,
                "candidate_statuses": [],
                "missing_requirements": ["Candidate A: pricing"],
                "other_material_gaps": [
                    "Candidate A: competition",
                    "Candidate A: demand",
                    "Candidate A: market_size",
                    "Candidate A: feasibility",
                ],
                "remediation_queries": [],
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

    assert report.critical_gaps == ["Candidate A: pricing"]
    assert set(report.other_material_gaps) == {
        "Candidate A: competition", "Candidate A: demand",
        "Candidate A: market_size", "Candidate A: feasibility",
    }
    text = report.to_text()
    assert "CRITICAL GAPS:\n  - Candidate A: pricing" in text
    assert "OTHER MATERIAL GAPS:" in text
    assert "Candidate A: competition" in text
