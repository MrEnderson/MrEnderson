"""Evidence-gap-driven research retries: gap detection, accumulation,
deduplication, resolution tracking, and the evidence-id propagation fix.
All offline — no network, no live API key anywhere in this file."""
from __future__ import annotations

from app.agents.research import _build_queries, MAX_FOLLOWUP_QUERIES
from app.agents.usage import ModelUsage, record_usage
from app.orchestration.evaluator import run_worker_with_qa
from app.schemas.agents import ExecutionOutput, QAVerdict, ResearchOutput
from app.schemas.evidence import EvidenceGap, EvidenceItem, canonical_url, merge_evidence_items
from app.security.evidence_qa import evaluate_evidence


# --- merge_evidence_items / canonical_url -----------------------------------


def test_canonical_url_normalizes_trivial_differences():
    a = canonical_url("HTTPS://Example.com/Path/")
    b = canonical_url("https://example.com/Path")
    assert a == b


def test_canonical_url_none_for_missing_url():
    assert canonical_url(None) is None
    assert canonical_url("") is None


def test_merge_evidence_items_deduplicates_by_canonical_url():
    existing = [EvidenceItem(claim="c1", source_url="https://example.com/a")]
    new = [
        EvidenceItem(claim="c1 restated", source_url="https://example.com/a/"),  # dup (trailing slash)
        EvidenceItem(claim="c2", source_url="https://example.com/b"),
    ]
    merged = merge_evidence_items(existing, new)
    assert len(merged) == 2
    assert merged[0].claim == "c1"  # first-seen wins, keeps original id
    urls = {e.source_url for e in merged}
    assert urls == {"https://example.com/a", "https://example.com/b"}


def test_merge_evidence_items_keeps_first_seen_id():
    original = EvidenceItem(claim="c1", source_url="https://example.com/a")
    dup = EvidenceItem(claim="c1 v2", source_url="https://example.com/a")
    merged = merge_evidence_items([original], [dup])
    assert len(merged) == 1
    assert merged[0].id == original.id


def test_merge_evidence_items_dedupes_urlless_items_by_claim():
    existing = [EvidenceItem(claim="same claim, no url")]
    new = [EvidenceItem(claim="same claim, no url"), EvidenceItem(claim="different claim")]
    merged = merge_evidence_items(existing, new)
    assert len(merged) == 2


def test_merge_evidence_items_never_grows_for_repeated_identical_queries():
    """Multiple queries returning the same page must not duplicate it."""
    existing: list[EvidenceItem] = []
    for _ in range(3):
        new = [EvidenceItem(claim="repeated", source_url="https://example.com/same")]
        existing = merge_evidence_items(existing, new)
    assert len(existing) == 1


# --- _build_queries (Research Agent follow-up query generation) ------------


def test_build_queries_uses_title_when_no_gaps():
    """v0.1.2.2 (Defect 1 fix): the broad first-attempt query is derived
    from the title, but Jarvis's own orchestration vocabulary
    ("opportunities") is stripped before it ever reaches an external
    search provider — see app/research_intelligence/query_builder.py. The
    query still targets the same underlying topic ("micro SaaS")."""
    queries = _build_queries(title="Find micro-SaaS opportunities", input_data={})
    assert queries == ["Find micro SaaS"]
    assert "opportunities" not in queries[0].lower()


def test_build_queries_uses_suggested_query_from_gaps():
    input_data = {
        "evidence_gaps": [
            {"gap_type": "competitor", "suggested_query": "micro SaaS competitors pricing 2026", "importance": 4},
        ]
    }
    queries = _build_queries(title="Find micro-SaaS opportunities", input_data=input_data)
    assert queries == ["micro SaaS competitors pricing 2026"]
    assert queries != ["Find micro-SaaS opportunities"]  # must differ from the original broad query


def test_build_queries_falls_back_to_title_plus_gap_type_phrase():
    input_data = {"evidence_gaps": [{"gap_type": "demand", "suggested_query": "", "importance": 3}]}
    queries = _build_queries(title="niche job boards", input_data=input_data)
    assert queries == ["niche job boards demand"]


def test_build_queries_is_bounded_and_ranked_by_importance():
    gaps = [
        {"gap_type": "other", "suggested_query": f"q{i}", "importance": i}
        for i in range(1, MAX_FOLLOWUP_QUERIES + 3)
    ]
    queries = _build_queries(title="t", input_data={"evidence_gaps": gaps})
    assert len(queries) == MAX_FOLLOWUP_QUERIES
    # highest importance gaps come first
    assert queries[0] == f"q{MAX_FOLLOWUP_QUERIES + 2}"


def test_build_queries_deduplicates_identical_suggested_queries():
    gaps = [
        {"gap_type": "pricing", "suggested_query": "same query", "importance": 3},
        {"gap_type": "competitor", "suggested_query": "same query", "importance": 3},
    ]
    queries = _build_queries(title="t", input_data={"evidence_gaps": gaps})
    assert queries == ["same query"]


# --- Structured gap detection (evidence_qa.py) ------------------------------


def _research_output(**overrides) -> dict:
    base = dict(
        question="micro-SaaS opportunities",
        findings=[],
        evidence=[],
        assumptions=[],
        unsupported_claims=[],
        open_questions=[],
        insufficient_evidence=True,
        summary="s",
    )
    base.update(overrides)
    return ResearchOutput(**base).model_dump(mode="json")


def test_gap_detection_matches_the_live_mission_examples():
    output = _research_output(
        unsupported_claims=[
            "No named competitors or pricing found for micro-SaaS.",
            "No demand signals or conversion benchmarks found.",
        ],
        open_questions=["What is the market size and growth rate?"],
    )
    check = evaluate_evidence(output)
    types = {g.gap_type for g in check.gaps}
    assert types == {"competitor", "pricing", "demand", "market_size", "growth_rate"}
    for gap in check.gaps:
        assert gap.suggested_query
        assert "micro-SaaS opportunities" in gap.suggested_query


def test_gap_detection_does_not_fire_when_evidence_is_sufficient():
    output = _research_output(insufficient_evidence=False, unsupported_claims=["market size mentioned"])
    check = evaluate_evidence(output)
    assert check.gaps == []


def test_gap_detection_does_not_fire_without_insufficiency_signal_text():
    output = _research_output(insufficient_evidence=True)
    check = evaluate_evidence(output)
    assert check.gaps == []


# --- Evaluator: accumulation + gap propagation + resolution (integration) ---


class _RecordingResearchWorker:
    """Stands in for ResearchAgent: returns pre-built ResearchOutputs and
    records what evidence_gaps each call received, so the evaluator's
    propagation/accumulation/resolution behavior can be checked directly."""

    def __init__(self, attempts: list[ResearchOutput]):
        self._attempts = attempts
        self.calls = 0
        self.received_gaps: list[list[dict]] = []

    async def run(self, *, title, description, input_data, context):
        self.received_gaps.append(input_data.get("evidence_gaps") or [])
        output = self._attempts[min(self.calls, len(self._attempts) - 1)]
        self.calls += 1
        return output


class _AlwaysPassQA:
    async def run(self, *, title, description, input_data, context):
        return QAVerdict(verdict="PASS", score=0.9, feedback="ok")


TOPIC = "micro-SaaS opportunities"


def _attempt_0() -> ResearchOutput:
    return ResearchOutput(
        question=TOPIC,
        findings=[],
        evidence=[
            EvidenceItem(claim="listicle 1", source_url="https://example.com/list1", query_used=TOPIC),
            EvidenceItem(claim="listicle 2", source_url="https://example.com/list2", query_used=TOPIC),
        ],
        assumptions=[],
        unsupported_claims=["No named competitors or pricing found for micro-SaaS."],
        open_questions=[],
        insufficient_evidence=True,
        summary="Broad research only.",
    )


def _attempt_1(competitor_query: str) -> ResearchOutput:
    return ResearchOutput(
        question=TOPIC,
        findings=[],
        evidence=[
            EvidenceItem(
                claim="Competitor X charges $9/mo",
                source_url="https://example.com/competitor-x",
                query_used=competitor_query,
            ),
        ],
        assumptions=[],
        unsupported_claims=["No pricing benchmark data found."],
        open_questions=[],
        insufficient_evidence=True,
        summary="Found a named competitor.",
    )


async def test_retry_receives_gaps_from_prior_attempt_as_context():
    worker = _RecordingResearchWorker([_attempt_0(), _attempt_1("placeholder")])
    await run_worker_with_qa(
        worker_agent=worker, qa_agent=_AlwaysPassQA(), title=TOPIC, description="",
        input_data={}, success_criteria=None, max_retries=1,
    )
    assert worker.received_gaps[0] == []  # first attempt: no gaps yet
    second_call_gap_types = {g["gap_type"] for g in worker.received_gaps[1]}
    assert "competitor" in second_call_gap_types
    assert "pricing" in second_call_gap_types


async def test_prior_evidence_survives_retry_and_new_evidence_accumulates():
    worker = _RecordingResearchWorker([_attempt_0(), _attempt_1("placeholder")])
    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=_AlwaysPassQA(), title=TOPIC, description="",
        input_data={}, success_criteria=None, max_retries=1,
    )
    urls = {e.source_url for e in result.output.evidence}
    assert urls == {
        "https://example.com/list1",
        "https://example.com/list2",
        "https://example.com/competitor-x",
    }


async def test_resolved_gap_is_marked_resolved_and_unresolved_gap_stays_visible():
    # Attempt 1's new evidence targets exactly the "competitor" gap's
    # suggested_query, computed the same way _detect_evidence_gaps builds it.
    competitor_query = f"{TOPIC} competitors"
    worker = _RecordingResearchWorker([_attempt_0(), _attempt_1(competitor_query)])
    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=_AlwaysPassQA(), title=TOPIC, description="",
        input_data={}, success_criteria=None, max_retries=1,
    )
    gaps_by_type = {g.gap_type: g for g in result.output.evidence_gaps}
    assert gaps_by_type["competitor"].resolved is True
    assert gaps_by_type["competitor"].supporting_evidence_ids
    assert gaps_by_type["pricing"].resolved is False  # still unresolved, still visible


async def test_stagnant_retry_stops_early_via_diminishing_returns():
    """Phase 4 diminishing-returns policy: repeating the SAME attempt (same
    evidence, same unresolved gaps, same score every time) is exactly the
    "wasted cycle" the policy exists to prevent — the loop stops after the
    first retry adds nothing, instead of blindly consuming the full
    max_retries budget. The very first retry is always given a chance
    (there's no baseline yet to judge it against)."""
    worker = _RecordingResearchWorker([_attempt_0(), _attempt_0(), _attempt_0(), _attempt_0()])
    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=_AlwaysPassQA(), title=TOPIC, description="",
        input_data={}, success_criteria=None, max_retries=2,
    )
    assert result.attempts_used == 1
    assert worker.calls == 2  # initial attempt + 1 retry that added nothing — then stops


async def test_retry_limit_still_respected_when_each_attempt_adds_value():
    """The max_retries ceiling still applies even when every attempt DOES
    show incremental value (a newly resolved competitor gap each time) —
    diminishing-returns never becomes a way to retry forever."""

    def _attempt_with_new_competitor(n: int, query: str) -> ResearchOutput:
        return ResearchOutput(
            question=TOPIC,
            findings=[],
            evidence=[
                EvidenceItem(
                    claim=f"Competitor {n} charges $9/mo",
                    source_url=f"https://example.com/competitor-{n}",
                    query_used=query,
                    evidence_depth="PAGE_EXTRACT",
                )
            ],
            assumptions=[],
            unsupported_claims=["No named competitors or pricing found for micro-SaaS."],
            open_questions=[],
            insufficient_evidence=True,
            summary=f"Found competitor {n}.",
        )

    competitor_query = f"{TOPIC} competitors"
    worker = _RecordingResearchWorker(
        [
            _attempt_0(),
            _attempt_with_new_competitor(1, competitor_query),
            _attempt_with_new_competitor(2, competitor_query),
            _attempt_with_new_competitor(3, competitor_query),
        ]
    )
    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=_AlwaysPassQA(), title=TOPIC, description="",
        input_data={}, success_criteria=None, max_retries=2,
    )
    assert result.attempts_used == 2
    assert worker.calls == 3  # initial attempt + 2 retries, never more — ceiling still holds


async def test_non_research_outputs_are_unaffected_by_accumulation_logic():
    """ExecutionOutput has no .evidence — the accumulation/gap machinery
    must be a complete no-op for it (regression guard for the generic loop)."""

    class _ExecWorker:
        async def run(self, *, title, description, input_data, context):
            return ExecutionOutput(actions_performed=["did a thing"])

    result = await run_worker_with_qa(
        worker_agent=_ExecWorker(), qa_agent=_AlwaysPassQA(), title="t", description="",
        input_data={}, success_criteria=None, max_retries=1,
    )
    assert result.verdict.verdict == "PASS"
    assert isinstance(result.output, ExecutionOutput)


# --- Evidence-id propagation / DB round-trip --------------------------------


async def test_evidence_id_survives_persistence_round_trip(session_factory):
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.services.evidence_service import EvidenceService
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("id@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        task = await TaskService(session).create_task(
            workspace_id=workspace.id, project_id=project.id, title="Research X", agent_type="research"
        )
        await session.commit()

        item = EvidenceItem(claim="c", source_url="https://example.com/a")
        original_id = item.id
        await EvidenceService(session).store_many(
            workspace_id=workspace.id, project_id=project.id, task_id=task.id, items=[item]
        )
        await session.commit()
        project_id = project.id

    async with session_factory() as session:
        stored = await EvidenceService(session).list_for_project(project_id)
        assert len(stored) == 1
        assert stored[0].id == original_id  # the DB row's id must match the schema's id, not a fresh uuid


async def test_evidence_id_survives_retry_and_persists_the_full_accumulated_set(session_factory):
    """End-to-end: a research task that retries and accumulates evidence
    persists ALL of it (not just the final attempt's delta) with stable ids."""
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import AgentExecutor
    from app.services.evidence_service import EvidenceService
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService
    from app.agents.registry import build_default_registry

    class _StubResearchAgent:
        def __init__(self, descriptor, provider=None):
            self.descriptor = descriptor
            self._worker = _RecordingResearchWorker(
                [_attempt_0(), _attempt_1(f"{TOPIC} competitors")]
            )

        async def run(self, **kwargs):
            return await self._worker.run(**kwargs)

    class _StubQAAgent:
        def __init__(self, descriptor, provider=None):
            self.descriptor = descriptor

        async def run(self, **kwargs):
            return QAVerdict(verdict="PASS", score=0.9, feedback="ok")

    registry = build_default_registry()
    registry.register(registry.get_descriptor("research"), _StubResearchAgent)
    registry.register(registry.get_descriptor("qa"), _StubQAAgent)

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("retry@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        await TaskService(session).create_task(
            workspace_id=workspace.id, project_id=project.id, title=TOPIC, agent_type="research"
        )
        await session.commit()
        workspace_id, project_id = workspace.id, project.id

    async with session_factory() as session:
        from app.orchestration import dispatcher

        await dispatcher.promote_ready_tasks(session, workspace_id=workspace_id, project_id=project_id)
        await session.commit()

    executor = AgentExecutor(session_factory, registry, provider=None)
    await executor.run_ready_tasks(workspace_id=workspace_id, project_id=project_id)

    async with session_factory() as session:
        stored = await EvidenceService(session).list_for_project(project_id)
        urls = {e.id: e.source_url for e in stored}
        assert len(stored) == 3  # both attempt-0 items plus attempt-1's new item, all persisted
        assert set(urls.values()) == {
            "https://example.com/list1",
            "https://example.com/list2",
            "https://example.com/competitor-x",
        }
