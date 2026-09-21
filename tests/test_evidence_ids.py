"""Evidence-id propagation: valid evidence_used ids from Strategy must
validate successfully wherever QA checks them — including the standalone
`qa` task, whose input_data never carries `research_results` at all (that
was the concrete, 100%-reproducible bug: see docs/evidence.md). Unknown ids
must still be rejected everywhere. Offline only — MockProvider throughout."""
from __future__ import annotations

from app.config.settings import get_settings
from app.orchestration.evaluator import run_worker_with_qa
from app.schemas.agents import QAVerdict, StrategyOutput
from app.schemas.evidence import EvidenceItem
from app.security.evidence_qa import evaluate_evidence


def _strategy_output(evidence_used: list[str]) -> dict:
    return {
        "options_considered": [],
        "recommendation": "Pursue option A",
        "reasoning": "Backed by cited evidence",
        "assumptions": ["general market conditions hold"],
        "evidence_used": evidence_used,
        "unsupported_claims": [],
        "confidence": 0.7,
    }


def test_valid_id_passes_via_known_evidence_ids_with_no_input_data():
    """This is exactly the standalone qa task's shape: no `research_results`
    in input_data at all, but a real evidence pool passed separately."""
    output = _strategy_output(["ev-1"])
    check = evaluate_evidence(output, input_data=None, known_evidence_ids={"ev-1", "ev-2"})
    assert check.needs_review is False


def test_valid_id_passes_via_input_data_alone_unchanged():
    output = _strategy_output(["ev-1"])
    check = evaluate_evidence(
        output, input_data={"research_results": [{"evidence": [{"id": "ev-1"}]}]}
    )
    assert check.needs_review is False


def test_unknown_id_still_rejected_even_with_known_evidence_ids_present():
    output = _strategy_output(["ev-does-not-exist"])
    check = evaluate_evidence(output, input_data=None, known_evidence_ids={"ev-1", "ev-2"})
    assert check.needs_review is True
    assert any("unknown evidence id" in issue for issue in check.issues)


def test_unknown_id_rejected_when_no_context_available_at_all():
    output = _strategy_output(["ev-1"])
    check = evaluate_evidence(output, input_data=None, known_evidence_ids=None)
    assert check.needs_review is True


def test_known_evidence_ids_and_input_data_are_unioned():
    output = _strategy_output(["from-db", "from-input"])
    check = evaluate_evidence(
        output,
        input_data={"research_results": [{"evidence": [{"id": "from-input"}]}]},
        known_evidence_ids={"from-db"},
    )
    assert check.needs_review is False


# --- Regression test: the standalone qa task's real _build_input shape -----


async def test_standalone_qa_task_validates_real_evidence_ids_end_to_end(session_factory):
    """Reproduces the exact live-mission bug: a strategy task's persisted
    output (with a real evidence_used id) reviewed by the planner's separate
    standalone `qa` task, whose input_data historically never included
    research_results. AgentExecutor must now pass known_evidence_ids sourced
    from the persisted Evidence table so this validates correctly."""
    from app.agents.registry import build_default_registry
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration import dispatcher
    from app.orchestration.executor import AgentExecutor
    from app.schemas.agents import QAVerdict, StrategyOutput
    from app.schemas.evidence import EvidenceItem
    from app.services.evidence_service import EvidenceService
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    # Known up front: EvidenceItem.id is generated at construction time, so
    # the stub agent below can close over the real id it should cite.
    evidence_item = EvidenceItem(claim="c", source_url="https://example.com/a")
    real_evidence_id = evidence_item.id

    class _StubStrategyAgent:
        def __init__(self, descriptor, provider=None):
            self.descriptor = descriptor

        async def run(self, **kwargs):
            return StrategyOutput(
                options_considered=[],
                recommendation="Pursue option A",
                reasoning="Backed by cited evidence",
                assumptions=["a"],
                evidence_used=[real_evidence_id],
            )

    class _StubQAAgent:
        def __init__(self, descriptor, provider=None):
            self.descriptor = descriptor

        async def run(self, **kwargs):
            return QAVerdict(verdict="PASS", score=0.9, feedback="looks fine")

    registry = build_default_registry()
    registry.register(registry.get_descriptor("strategy"), _StubStrategyAgent)
    registry.register(registry.get_descriptor("qa"), _StubQAAgent)

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("qa-ids@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        task_service = TaskService(session)

        strategy_task = await task_service.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Strategy", agent_type="strategy"
        )
        qa_task = await task_service.create_task(
            workspace_id=workspace.id,
            project_id=project.id,
            title="QA review",
            agent_type="qa",
            depends_on_task_ids=[strategy_task.id],
        )

        # Persist real evidence for this project, as a completed research
        # task would have — this is the id Strategy's evidence_used cites.
        await EvidenceService(session).store_many(
            workspace_id=workspace.id,
            project_id=project.id,
            task_id=strategy_task.id,
            items=[evidence_item],
        )
        await session.commit()
        workspace_id, project_id, qa_task_id = workspace.id, project.id, qa_task.id

    async with session_factory() as session:
        await dispatcher.promote_ready_tasks(session, workspace_id=workspace_id, project_id=project_id)
        await session.commit()

    executor = AgentExecutor(session_factory, registry, provider=None)
    await executor.run_ready_tasks(workspace_id=workspace_id, project_id=project_id)  # runs strategy

    async with session_factory() as session:
        await dispatcher.promote_ready_tasks(session, workspace_id=workspace_id, project_id=project_id)
        await session.commit()

    await executor.run_ready_tasks(workspace_id=workspace_id, project_id=project_id)  # runs qa

    async with session_factory() as session:
        qa_task_row = await TaskService(session).get(qa_task_id)
        output = TaskService.parse_output(qa_task_row)
        assert output is not None
        assert output["verdict"] == "PASS"
        assert not any("unknown evidence id" in issue for issue in output.get("issues", []))


# --- Phase 6: compaction-aware evidence-id validation (integration) --------
#
# Once app/agents/strategy_context.py bounds what Strategy sees each attempt,
# validation must be restricted to what was ACTUALLY shown this attempt, not
# the full project-wide evidence pool — otherwise a real-but-compacted-out id
# could accidentally validate even though the model never saw it. See
# app/orchestration/evaluator.py::run_worker_with_qa.


async def test_compacted_out_evidence_cannot_be_cited_unless_visible(monkeypatch):
    monkeypatch.setenv("STRATEGY_MAX_EVIDENCE_ITEMS", "1")
    get_settings.cache_clear()

    excluded = EvidenceItem(
        claim="c-excluded", source_url="https://example.com/weak",
        evidence_depth="SEARCH_SNIPPET", source_quality="UNKNOWN",
    )
    included = EvidenceItem(
        claim="c-included", source_url="https://example.com/strong",
        evidence_depth="PAGE_EXTRACT", source_quality="AUTHORITATIVE",
    )
    research_results = [
        {
            "task_id": "r1",
            "title": "Research",
            "agent_type": "research",
            "evidence": [excluded.model_dump(mode="json"), included.model_dump(mode="json")],
        }
    ]

    class _StubStrategy:
        async def run(self, *, title, description, input_data, context):
            return StrategyOutput(
                options_considered=[], recommendation="r", reasoning="x",
                assumptions=["a"], evidence_used=[excluded.id],
            )

    class _AlwaysPassQA:
        async def run(self, **kwargs):
            return QAVerdict(verdict="PASS", score=0.9, feedback="ok")

    try:
        result = await run_worker_with_qa(
            worker_agent=_StubStrategy(), qa_agent=_AlwaysPassQA(), title="t", description="",
            input_data={"research_results": research_results}, success_criteria=None, max_retries=0,
            # Both ids are REAL, persisted, project-wide — `excluded` is only
            # missing from what THIS attempt actually showed the model.
            known_evidence_ids={excluded.id, included.id},
        )
    finally:
        get_settings.cache_clear()

    assert result.verdict.verdict == "NEEDS_REVIEW"
    assert any("unknown evidence id" in i for i in result.verdict.issues)
    # Retry feedback explicitly names which id was invalid.
    assert excluded.id in result.verdict.feedback


async def test_clearly_hallucinated_id_is_rejected():
    research_results = [
        {"task_id": "r1", "evidence": [EvidenceItem(claim="c", source_url="https://example.com/a").model_dump(mode="json")]}
    ]

    class _StubStrategy:
        async def run(self, *, title, description, input_data, context):
            return StrategyOutput(
                options_considered=[], recommendation="r", reasoning="x",
                assumptions=["a"], evidence_used=["00000000-0000-0000-0000-000000000000"],
            )

    class _AlwaysPassQA:
        async def run(self, **kwargs):
            return QAVerdict(verdict="PASS", score=0.9, feedback="ok")

    result = await run_worker_with_qa(
        worker_agent=_StubStrategy(), qa_agent=_AlwaysPassQA(), title="t", description="",
        input_data={"research_results": research_results}, success_criteria=None, max_retries=0,
    )
    assert result.verdict.verdict == "NEEDS_REVIEW"
    assert any("unknown evidence id" in i for i in result.verdict.issues)


async def test_evidence_cited_on_a_prior_attempt_remains_valid_on_retry(monkeypatch):
    """The id an earlier attempt legitimately cited must survive compaction
    on a retry (pinning — see app/agents/strategy_context.py), even when a
    higher-quality item would otherwise have displaced it from the bounded
    evidence shown. No replacement id is ever generated for it."""
    monkeypatch.setenv("STRATEGY_MAX_EVIDENCE_ITEMS", "1")
    get_settings.cache_clear()

    cited = EvidenceItem(
        claim="c1", source_url="https://example.com/weak",
        evidence_depth="SEARCH_SNIPPET", source_quality="UNKNOWN",
    )
    stronger = EvidenceItem(
        claim="c2", source_url="https://example.com/strong",
        evidence_depth="PAGE_EXTRACT", source_quality="AUTHORITATIVE",
    )
    research_results = [
        {"task_id": "r1", "evidence": [cited.model_dump(mode="json"), stronger.model_dump(mode="json")]}
    ]
    original_id = cited.id

    class _StubStrategy:
        async def run(self, *, title, description, input_data, context):
            return StrategyOutput(
                options_considered=[], recommendation="r", reasoning="x",
                assumptions=["a"], evidence_used=[original_id],
            )

    class _QASequence:
        def __init__(self):
            self.calls = 0

        async def run(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return QAVerdict(verdict="NEEDS_REVIEW", score=0.5, feedback="add more detail")
            return QAVerdict(verdict="PASS", score=0.9, feedback="ok")

    try:
        result = await run_worker_with_qa(
            worker_agent=_StubStrategy(), qa_agent=_QASequence(), title="t", description="",
            input_data={"research_results": research_results}, success_criteria=None, max_retries=1,
        )
    finally:
        get_settings.cache_clear()

    assert result.verdict.verdict == "PASS"
    assert not any("unknown evidence id" in i for i in result.verdict.issues)
    assert result.output.evidence_used == [original_id]  # same id, never regenerated
