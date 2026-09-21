"""v0.1.2.3 Defect 1: evidence provenance metadata and the hard validation
invariants — evidence for Notion Template Marketplace never satisfies Coda Template Hub,
DISCOVERY/unrelated-task evidence never counts toward VALIDATION coverage,
and REJECT evidence never counts toward coverage. Offline."""
from __future__ import annotations

import uuid

from app.config.settings import Settings
from app.research_intelligence.gate import evaluate_comparison_readiness
from app.schemas.evidence import EvidenceItem


def _item(url: str, claim: str, **overrides) -> dict:
    base = {"id": str(uuid.uuid4()), "claim": claim, "source_url": url, "excerpt": claim}
    base.update(overrides)
    return base


def _full_coverage_evidence(label: str, *, research_mode: str = "VALIDATION") -> list[dict]:
    return [
        _item("https://www.producthunt.com/posts/x", f"{label}: strong demand with growing traction on Product Hunt.", research_mode=research_mode),
        _item("https://www.similarweb.com/website/x", f"Similarweb traffic data shows strong demand and traction for {label}.", research_mode=research_mode),
        _item("https://www.producthunt.com/posts/y", f"{label}: named competitors identified among similar launches.", research_mode=research_mode),
        _item("https://www.g2.com/products/x", f"G2 reviews list several competitors to {label}.", research_mode=research_mode),
        _item("https://gumroad.com/l/x", f"Gumroad marketplace pricing for {label} listed clearly.", research_mode=research_mode),
        _item("https://appsumo.com/products/x", f"AppSumo pricing deal for {label} shows plan tiers.", research_mode=research_mode),
        _item("https://reddit.com/r/x/comments/1", f"Reddit users report a common pain point and complain about {label}.", research_mode=research_mode),
        _item("https://www.indiehackers.com/post/1", f"Indie Hackers discussion: customers complain about a pain point with {label}.", research_mode=research_mode),
        _item("https://www.statista.com/statistics/x", f"Statista data on market size and total addressable market for {label}.", research_mode=research_mode),
        _item("https://www.gartner.com/reports/x", f"Gartner report on market size for {label}.", research_mode=research_mode),
        _item("https://www.g2.com/products/y", f"G2 reviews discuss technical feasibility of building {label}.", research_mode=research_mode),
    ]


def _research_result(title: str, evidence: list[dict], *, candidates: list[dict] | None = None) -> dict:
    result = {"task_id": title, "title": title, "question": title, "evidence": evidence}
    if candidates is not None:
        result["candidates"] = candidates
    return result


# --- 1. VALIDATION evidence retains originating query -----------------------


async def test_validation_evidence_retains_originating_query():
    from app.agents.research import ResearchAgent
    from app.database.models import PermissionLevel
    from app.schemas.agents import AgentDescriptor
    from app.schemas.research_dto import ValidationModelOutput
    from app.tools.research_tools import SearchResult

    class _Provider:
        name = "fake"
        is_live = True

        async def search(self, query, *, max_results=5):
            return [SearchResult(title="t", url="https://example.com/a", snippet=f"About {query}")]

        async def fetch(self, url):
            raise NotImplementedError

        async def extract(self, content, question):
            raise NotImplementedError

    class _Model:
        name = "stub"

        async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
            return ValidationModelOutput(summary="s")

    descriptor = AgentDescriptor(
        name="research", role="research", description="research", capabilities=[],
        permissions=[PermissionLevel.READ], model="mock-model",
    )
    agent = ResearchAgent(descriptor=descriptor, provider=_Model(), research_provider=_Provider())
    result = await agent.run(
        title="Validate and compare candidate opportunities",
        description="",
        input_data={
            "research_mode": "VALIDATION",
            "candidates": [{"id": "a", "label": "Notion Template Marketplace"}],
            "task_id": "task-123",
            # Normally set by app/orchestration/evaluator.py's retry loop;
            # simulated here since this test calls ResearchAgent directly.
            "attempt_number": 0,
        },
        context={},
    )
    assert result.evidence
    for item in result.evidence:
        assert item.query_used  # originating_query
        assert item.research_mode == "VALIDATION"
        assert item.research_task_id == "task-123"
        assert item.attempt_number == 0


# --- 2. Notion Template Marketplace evidence cannot satisfy candidate B's requirement ------


def test_candidate_a_evidence_never_satisfies_candidate_b_coverage():
    settings = Settings()
    evidence_a = _full_coverage_evidence("Notion Template Marketplace")
    # Coda Template Hub has NO evidence of its own — only Notion Template Marketplace's evidence
    # is present in the research_results.
    research_results = [
        _research_result(
            "validation-1",
            evidence_a,
            candidates=[{"label": "Notion Template Marketplace"}, {"label": "Coda Template Hub"}],
        )
    ]
    readiness = evaluate_comparison_readiness(research_results, settings=settings)
    statuses = {s.candidate_label: s for s in readiness.candidate_statuses}
    assert statuses["Notion Template Marketplace"].ready_for_comparison is True
    assert statuses["Coda Template Hub"].ready_for_comparison is False
    assert statuses["Coda Template Hub"].coverage_percentage == 0.0
    assert readiness.ready is False


# --- 3. Discovery evidence cannot automatically satisfy validation coverage


def test_discovery_tagged_evidence_excluded_from_validation_coverage():
    settings = Settings()
    # Evidence explicitly tagged as having come from a DISCOVERY task —
    # even if it's plausible-looking, comprehensive evidence, it must NOT
    # count toward VALIDATION coverage.
    discovery_evidence = _full_coverage_evidence("Notion Template Marketplace", research_mode="DISCOVERY")
    research_results = [
        _research_result(
            "validation-1",
            discovery_evidence,
            candidates=[{"label": "Notion Template Marketplace"}, {"label": "Coda Template Hub"}],
        )
    ]
    readiness = evaluate_comparison_readiness(research_results, settings=settings)
    statuses = {s.candidate_label: s for s in readiness.candidate_statuses}
    assert statuses["Notion Template Marketplace"].coverage_percentage == 0.0
    assert statuses["Notion Template Marketplace"].ready_for_comparison is False
    assert readiness.ready is False


# --- 4. Unrelated previous-task (GENERAL) evidence cannot enter coverage ---


def test_general_mode_tagged_evidence_excluded_from_validation_coverage():
    settings = Settings()
    general_evidence = _full_coverage_evidence("Notion Template Marketplace", research_mode="GENERAL")
    research_results = [
        _research_result(
            "validation-1",
            general_evidence,
            candidates=[{"label": "Notion Template Marketplace"}, {"label": "Coda Template Hub"}],
        )
    ]
    readiness = evaluate_comparison_readiness(research_results, settings=settings)
    statuses = {s.candidate_label: s for s in readiness.candidate_statuses}
    assert statuses["Notion Template Marketplace"].coverage_percentage == 0.0


def test_untagged_legacy_evidence_still_works_for_backward_compatibility():
    """Evidence with research_mode=None (hand-built/legacy) is still
    accepted — the exclusion only applies to evidence EXPLICITLY tagged as
    a non-VALIDATION mode."""
    settings = Settings()
    untagged_evidence = _full_coverage_evidence("Notion Template Marketplace", research_mode=None)
    for item in untagged_evidence:
        item.pop("research_mode", None)
    research_results = [
        _research_result(
            "validation-1",
            untagged_evidence,
            candidates=[{"label": "Notion Template Marketplace"}, {"label": "Coda Template Hub"}],
        )
    ]
    readiness = evaluate_comparison_readiness(research_results, settings=settings)
    statuses = {s.candidate_label: s for s in readiness.candidate_statuses}
    assert statuses["Notion Template Marketplace"].coverage_percentage == 1.0


# --- 5. REJECT evidence never counts toward coverage ------------------------


def test_reject_relevance_evidence_never_counts_toward_coverage():
    settings = Settings()
    off_topic = [
        _item(
            "https://random-blog.example.com/top10",
            "Top 10 best ways to make money online with digital products.",
            research_mode="VALIDATION",
        )
    ]
    research_results = [
        _research_result(
            "validation-1", off_topic, candidates=[{"label": "Notion Template Marketplace"}, {"label": "Coda Template Hub"}]
        )
    ]
    readiness = evaluate_comparison_readiness(research_results, settings=settings)
    statuses = {s.candidate_label: s for s in readiness.candidate_statuses}
    assert all(s.coverage_percentage == 0.0 for s in statuses.values())


# --- 6. Retry evidence accumulation preserves authoritative valid evidence -


async def test_retry_accumulation_preserves_all_valid_evidence_across_attempts():
    from app.orchestration.evaluator import run_worker_with_qa
    from app.schemas.agents import QAVerdict, ResearchOutput
    from app.schemas.evidence import EvidenceItem as EI

    class _Worker:
        def __init__(self):
            self.calls = 0

        async def run(self, *, title, description, input_data, context):
            self.calls += 1
            return ResearchOutput(
                question="q",
                findings=[],
                evidence=[EI(claim=f"c{self.calls}", source_url=f"https://example.com/{self.calls}")],
                insufficient_evidence=True,
                summary="s",
            )

    class _QA:
        def __init__(self):
            self.calls = 0

        async def run(self, **kwargs):
            self.calls += 1
            return QAVerdict(
                verdict="PASS" if self.calls >= 3 else "NEEDS_REVIEW",
                score=0.9 if self.calls >= 3 else 0.3 + self.calls * 0.1,
                feedback="ok",
            )

    result = await run_worker_with_qa(
        worker_agent=_Worker(), qa_agent=_QA(), title="t", description="",
        input_data={}, success_criteria=None, max_retries=5,
    )
    # Every attempt's evidence survives in the authoritative accumulated
    # pool, regardless of how many attempts happened.
    assert len(result.accumulated_evidence) == result.attempts_used + 1


# --- 9. Full authoritative evidence still reaches the completeness gate ---


def test_full_authoritative_evidence_reaches_completeness_gate_with_provenance():
    settings = Settings()
    research_results = [
        _research_result(
            "validation-1",
            _full_coverage_evidence("Notion Template Marketplace") + _full_coverage_evidence("Coda Template Hub"),
            candidates=[{"label": "Notion Template Marketplace"}, {"label": "Coda Template Hub"}],
        )
    ]
    readiness = evaluate_comparison_readiness(research_results, settings=settings)
    assert readiness.ready is True
    assert len(readiness.candidate_statuses) == 2
