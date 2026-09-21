"""v0.1.2.5 Phase 15: offline retrieval-quality benchmark for the three
live candidate concepts. Feeds a mixed batch of synthetic search results
(exactly the checkpoint's named mix) through the SAME tagging + Admission
Gate pipeline twice — BEFORE (no pre-screen: every raw result reaches
tagging/admission, the v0.1.2.4 behavior) and AFTER (v0.1.2.5's
pre-screen applied first) — and prints BEFORE/AFTER metrics. The
Admission Gate's own thresholds are IDENTICAL in both runs (Phase 12: do
not loosen them to manufacture an improvement) — only what reaches it
changes. Offline — no network call.
"""
from __future__ import annotations

from app.config.settings import Settings
from app.research_intelligence.admission import apply_admission_gate
from app.research_intelligence.prescreen import prescreen_search_result
from app.research_intelligence.query_builder import build_candidate_concepts
from app.research_intelligence.requirements import generate_requirement_set
from app.research_intelligence.tagging import tag_evidence_for_candidate
from app.schemas.evidence import EvidenceItem
from app.tools.research_tools import SearchResult

CANDIDATE_LABEL = "AI-Powered Content Creation Tools & Templates"
CANDIDATE_DESCRIPTION = "A marketplace of AI prompt templates and workflow automation for small businesses."


def _mixed_search_results() -> list[SearchResult]:
    return [
        SearchResult(  # genuinely relevant pricing evidence
            title="AI Content Tool Pricing Plans",
            url="https://www.g2.com/products/ai-content-tool",
            snippet="AI content creation tool pricing plans start at $29/month for small businesses.",
        ),
        SearchResult(  # genuinely relevant competitor evidence
            title="Top AI Content Creation Competitors",
            url="https://www.capterra.com/ai-content-tools",
            snippet="Leading AI content creation and prompt template competitors compared side by side.",
        ),
        SearchResult(  # HR candidate-assessment result (noise)
            title="Candidate Experience Statistics and ATS Market Report",
            url="https://www.grandviewresearch.com/candidate-assessment-market",
            snippet="The global candidate assessment and applicant tracking system market size...",
        ),
        SearchResult(  # political candidate result (noise)
            title="Political Candidate Election Fundraising Report",
            url="https://example-news.com/election-2026",
            snippet="The political candidate's campaign donation totals ahead of the primary election.",
        ),
        SearchResult(  # generic SEO blog
            title="Top 10 Best Ways to Make Money Online with Digital Products",
            url="https://example-blog.com/make-money-online",
            snippet="Top 10 best ways to make money online with digital products and side hustles.",
        ),
        SearchResult(  # wrong-market Statista report
            title="Statista: Background Screening Industry Market Size",
            url="https://www.statista.com/statistics/background-screening-market-size",
            snippet="Statista market research on the background screening and pre-employment vetting industry.",
        ),
        SearchResult(  # candidate-specific primary pricing page
            title="AI Content Tool Pricing",
            url="https://www.example-ai-content-tool.com/pricing",
            snippet="Our AI content creation and prompt template plans start at $19/month, $49/month for teams.",
        ),
        SearchResult(  # marketplace product/listing
            title="AI Prompt Template Bundle",
            url="https://gumroad.com/l/ai-prompt-template-bundle",
            snippet="A bundle of AI content creation prompt templates for small business marketing, $15.",
        ),
        SearchResult(  # relevant commercial market report
            title="AI Content Creation Software Market Size Report",
            url="https://www.grandviewresearch.com/industry-analysis/ai-content-creation-market",
            snippet="The AI content creation software market size for small businesses was valued using vendor revenue.",
        ),
    ]


def _run_pipeline(results: list[SearchResult], *, apply_prescreen: bool, settings: Settings) -> list[EvidenceItem]:
    concepts = build_candidate_concepts(CANDIDATE_LABEL, CANDIDATE_DESCRIPTION)
    if apply_prescreen:
        results = [r for r in results if prescreen_search_result(r, concepts=concepts)]

    items = [
        EvidenceItem(
            claim=r.snippet, source_title=r.title, source_url=r.url, excerpt=r.snippet,
            query_used="benchmark query", research_mode="VALIDATION",
        )
        for r in results
    ]
    requirements = generate_requirement_set(candidate_id="c", candidate_label=CANDIDATE_LABEL, settings=settings)
    tagged = tag_evidence_for_candidate(
        items, candidate_id="c", candidate_label=CANDIDATE_LABEL, requirements=requirements
    )
    return apply_admission_gate(tagged, candidates_by_id={"c": (CANDIDATE_LABEL, CANDIDATE_DESCRIPTION)}, settings=settings)


def _print_metrics(label: str, results_returned: int, stamped: list[EvidenceItem], prescreen_rejected: int) -> dict:
    accepted = sum(1 for i in stamped if i.admission_status == "ACCEPTED")
    rejected = sum(1 for i in stamped if i.admission_status == "REJECTED")
    gate_evaluated = accepted + rejected
    metrics = {
        "results_returned": results_returned,
        "pre_screen_rejected": prescreen_rejected,
        "admission_rejected": rejected,
        "accepted": accepted,
        # Checkpoint's own formula: accepted / raw results retrieved. This
        # does NOT move from pre-screening alone — retrieval itself (what
        # Tavily returns) is unchanged; only what happens to it next
        # changes. Kept for direct comparison against the live benchmark's
        # own numbers.
        "accepted_evidence_yield": accepted / max(results_returned, 1),
        # The metric pre-screening actually improves: of what's SENT to
        # the (unweakened) Admission Gate, how much of it is worth
        # evaluating at all. Fewer gate-evaluated noise items also means
        # fewer wasted Tavily PAGE_EXTRACT calls upstream (Phase 6).
        "admission_gate_precision": accepted / max(gate_evaluated, 1),
        "gate_evaluated": gate_evaluated,
    }
    print(f"{label}: {metrics}")
    return metrics


def test_prescreen_reduces_admission_gate_burden_without_weakening_it_or_losing_real_evidence():
    settings = Settings()
    results = _mixed_search_results()

    before = _run_pipeline(results, apply_prescreen=False, settings=settings)
    before_metrics = _print_metrics("BEFORE (no pre-screen)", len(results), before, prescreen_rejected=0)

    concepts = build_candidate_concepts(CANDIDATE_LABEL, CANDIDATE_DESCRIPTION)
    prescreen_rejected = sum(1 for r in results if not prescreen_search_result(r, concepts=concepts))
    after = _run_pipeline(results, apply_prescreen=True, settings=settings)
    after_metrics = _print_metrics("AFTER (with pre-screen)", len(results), after, prescreen_rejected=prescreen_rejected)

    # Phase 12 invariant: the Admission Gate's own settings are untouched
    # (both runs used the SAME Settings object) — any improvement comes
    # from upstream retrieval quality, never a loosened gate.
    assert prescreen_rejected >= 2  # the HR + political noise items must be caught before the gate ever sees them
    # The official checkpoint metric (accepted / raw results) is
    # retrieval-bound, not pre-screen-bound — it must never DROP (no real
    # evidence lost), and here stays flat since retrieval itself didn't
    # change:
    assert after_metrics["accepted"] == before_metrics["accepted"]
    assert after_metrics["accepted_evidence_yield"] >= before_metrics["accepted_evidence_yield"]
    # What pre-screening materially improves: less noise reaches the
    # (unweakened) gate at all, for the exact same accepted count —
    # higher admission-gate precision, fewer wasted extraction/tagging
    # cycles on items that were always going to be rejected anyway.
    assert after_metrics["gate_evaluated"] < before_metrics["gate_evaluated"]
    assert after_metrics["admission_gate_precision"] > before_metrics["admission_gate_precision"]
    # The genuinely relevant items must survive in BOTH runs — pre-screen
    # must never remove real evidence, only noise.
    assert any("g2.com" in (i.source_url or "") for i in after if i.admission_status == "ACCEPTED")
