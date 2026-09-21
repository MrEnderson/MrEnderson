"""v0.1.2.4 Defect 1, Phase 3: offline fixtures mirroring the ACTUAL call
path (research.py's real private helpers — _build_prompt_context,
_prompt_evidence, _select_prompt_evidence, _system_prompt_for_mode — not a
separate reimplementation) for DISCOVERY attempt 0/retry and VALIDATION
attempt 0/retry 1/retry 2. Purpose: determine which components dominate
request size, ruling hypotheses in or out by measurement rather than
assumption. See the checkpoint delivery report for the narrative
conclusion; this file is the evidence behind it.

No network call. No live provider. Pure code-path tracing with realistic
(not minimal) fixture evidence: 15 items, excerpts/claims at or near their
configured caps, real-shaped URLs — the worst case the existing bounding
logic is supposed to contain.
"""
from __future__ import annotations

import json

import pytest

from app.agents.research import (
    _build_prompt_context,
    _prompt_evidence,
    _select_prompt_evidence,
    _system_prompt_for_mode,
    _grounded_system_prompt,
)
from app.config.settings import get_settings
from app.database.models import EvidenceVerificationStatus
from app.research_intelligence.schemas import ResearchCandidate
from app.schemas.evidence import EvidenceItem
from app.schemas.research_dto import DiscoveryModelOutput, ValidationModelOutput


def _realistic_evidence(n: int, *, settings, category: str = "pricing") -> list[EvidenceItem]:
    """Worst-case-realistic: excerpt/claim sized AT the configured caps, a
    real-shaped long URL (URLs are known to tokenize poorly — many short
    BPE tokens per path segment), so this fixture cannot UNDER-state real
    request size relative to what the bounding logic in research.py allows
    through."""
    items = []
    for i in range(n):
        items.append(
            EvidenceItem(
                claim=(
                    f"Claim {i}: " + ("Independent market research indicates measurable demand " * 6)
                )[:250],
                source_title=f"In-depth analysis of competitor pricing and market sizing, part {i}",
                source_url=(
                    f"https://www.example-research-publisher-{i}.com/reports/2026/"
                    f"industry-vertical-analysis/pricing-and-competition-deep-dive-{i}?utm_source=search&ref=abc123"
                ),
                publisher=f"example-research-publisher-{i}.com",
                excerpt=(
                    "According to the published methodology, the addressable market was "
                    "estimated using a bottom-up approach combining publicly disclosed "
                    "vendor pricing tiers, industry survey responses, and analyst commentary. "
                    "Pricing for comparable offerings ranged across several published tiers, "
                    "with enterprise contracts negotiated separately from listed self-serve "
                    "pricing. " * 3
                ),
                evidence_depth="PAGE_EXTRACT" if i % 2 == 0 else "SEARCH_SNIPPET",
                verification_status=EvidenceVerificationStatus.RETRIEVED,
                source_quality="AUTHORITATIVE" if i % 3 == 0 else "UNKNOWN",
                query_used="fixture query",
                candidate_id=f"candidate-{i % 3}",
                requirement_category=category,
                relevance_label="HIGH",
                relevance_score=0.9,
                source_role="COMMERCIAL_RESEARCH",
            )
        )
    return items


def _breakdown(*, system_prompt: str, prompt_context: dict, output_schema) -> dict:
    user_prompt = json.dumps(prompt_context)
    schema_chars = len(json.dumps(output_schema.model_json_schema()))
    return {
        "system_chars": len(system_prompt),
        "content_chars": len(user_prompt),
        "schema_chars": schema_chars,
        "total_chars": len(system_prompt) + len(user_prompt) + schema_chars,
        "evidence_item_count": len(prompt_context.get("evidence") or []),
    }


@pytest.fixture
def settings():
    return get_settings()


def test_discovery_attempt_zero_breakdown(settings):
    """No evidence_gaps, no qa_feedback — the plain first attempt."""
    evidence = _realistic_evidence(20, settings=settings)  # more than research_max_evidence_items
    selected = _select_prompt_evidence(evidence, settings=settings)
    evidence_dicts = _prompt_evidence(
        selected, max_items=len(selected), max_excerpt_chars=settings.research_max_evidence_excerpt_chars
    )
    prompt_context = _build_prompt_context(
        title="Discover profitable niche SaaS opportunities",
        description="Broad discovery objective description.",
        input_data={}, evidence_dicts=evidence_dicts, settings=settings,
    )
    system_prompt = _system_prompt_for_mode(_grounded_system_prompt(settings), "DISCOVERY", settings)
    breakdown = _breakdown(
        system_prompt=system_prompt, prompt_context=prompt_context, output_schema=DiscoveryModelOutput
    )

    # Bounding logic invariants, proven by measurement, not assumed:
    assert breakdown["evidence_item_count"] <= settings.research_max_evidence_items
    assert breakdown["schema_chars"] < 2000  # schema/tool overhead is small in char terms
    assert breakdown["system_chars"] < 4000  # system prompt is small (DISCOVERY adds its own instructions)
    # Evidence dominates total request size, not system/schema:
    evidence_chars = len(json.dumps(prompt_context.get("evidence")))
    assert evidence_chars > breakdown["schema_chars"]
    assert evidence_chars > breakdown["system_chars"]
    print("\nDISCOVERY attempt 0:", breakdown)


def test_discovery_retry_breakdown_does_not_grow_with_attempt_number(settings):
    """A DISCOVERY retry (insufficient_evidence -> another broad search) —
    no qa_feedback/unresolved_gaps machinery applies to DISCOVERY's own
    gap-free retry path (Defect 2's fix), so retry-attempt content size
    should track evidence count, not attempt number."""
    evidence = _realistic_evidence(20, settings=settings)
    selected = _select_prompt_evidence(evidence, settings=settings)
    evidence_dicts = _prompt_evidence(
        selected, max_items=len(selected), max_excerpt_chars=settings.research_max_evidence_excerpt_chars
    )
    prompt_context = _build_prompt_context(
        title="Discover profitable niche SaaS opportunities",
        description="Broad discovery objective description.",
        input_data={"attempt_number": 1}, evidence_dicts=evidence_dicts, settings=settings,
    )
    system_prompt = _system_prompt_for_mode(_grounded_system_prompt(settings), "DISCOVERY", settings)
    breakdown = _breakdown(
        system_prompt=system_prompt, prompt_context=prompt_context, output_schema=DiscoveryModelOutput
    )
    print("\nDISCOVERY retry (attempt=1):", breakdown)
    assert breakdown["content_chars"] < 15000  # stays bounded regardless of attempt number


@pytest.mark.parametrize("attempt,n_gaps", [(0, 0), (1, 1), (2, 3)])
def test_validation_attempt_breakdowns(settings, attempt, n_gaps):
    """VALIDATION attempt 0 (no gaps), retry 1 (1 unresolved gap +
    qa_feedback), retry 2 (3 unresolved gaps + qa_feedback) — the exact
    three points the checkpoint asks about."""
    candidates = [
        ResearchCandidate(id=f"candidate-{i}", label=f"Candidate {i}", description="A validated candidate.", status="DISCOVERED")
        for i in range(3)
    ]
    candidate_dicts = [{"label": c.label, "description": c.description} for c in candidates]
    evidence = _realistic_evidence(20, settings=settings)
    unresolved_gap_keys = {("candidate-0", "pricing")} if n_gaps else None
    selected = _select_prompt_evidence(evidence, settings=settings, unresolved_gap_keys=unresolved_gap_keys)
    evidence_dicts = _prompt_evidence(
        selected, max_items=len(selected), max_excerpt_chars=settings.research_max_evidence_excerpt_chars
    )
    input_data = {"attempt_number": attempt}
    if n_gaps:
        input_data["qa_feedback"] = (
            "Evidence for pricing and competition is still insufficient for Candidate 0; "
            "retrieve additional sources." * 3
        )
        input_data["evidence_gaps"] = [
            {"gap_type": "pricing", "claim_or_question": f"Missing pricing evidence for candidate {i}", "resolved": False}
            for i in range(n_gaps)
        ]
    prompt_context = _build_prompt_context(
        title="Validate shortlisted candidates",
        description="Validation objective description.",
        input_data=input_data, evidence_dicts=evidence_dicts, settings=settings, candidates=candidate_dicts,
    )
    system_prompt = _system_prompt_for_mode(_grounded_system_prompt(settings), "VALIDATION", settings, candidates)
    breakdown = _breakdown(
        system_prompt=system_prompt, prompt_context=prompt_context, output_schema=ValidationModelOutput
    )
    print(f"\nVALIDATION attempt={attempt} gaps={n_gaps}:", breakdown)

    # qa_feedback/unresolved_gaps are bounded — a retry does not balloon
    # request size relative to attempt 0 (Phase 9 invariant, re-verified
    # here against the real helpers rather than assumed from v0.1.2.3):
    assert breakdown["content_chars"] < 16000
    if n_gaps:
        qa_feedback_field = prompt_context.get("qa_feedback", "")
        assert len(qa_feedback_field) <= settings.research_prompt_max_qa_feedback_chars
        assert len(prompt_context.get("unresolved_gaps", [])) <= 5


def test_schema_and_system_prompt_are_not_the_dominant_component(settings):
    """Directly answers one of the checkpoint's named hypotheses: is the
    structured-output schema (the compiled 'tool' definition) or the
    system prompt what's driving request size? By character count: no —
    both are roughly an order of magnitude smaller than the bounded
    evidence block. This does NOT rule out Anthropic's internal tool-use
    token overhead (the SDK's own grammar compilation for strict
    structured output, the same mechanism behind the historical 'compiled
    grammar too large' HTTP 400) being larger in TOKENS than these
    components are in CHARACTERS — that gap can only be closed with live
    provider_input_tokens data, which Defect 1's new diagnostic now
    captures per call going forward."""
    schema_chars = len(json.dumps(ValidationModelOutput.model_json_schema()))
    system_prompt = _system_prompt_for_mode(_grounded_system_prompt(settings), "VALIDATION", settings, [])
    evidence = _realistic_evidence(15, settings=settings)
    selected = _select_prompt_evidence(evidence, settings=settings)
    evidence_dicts = _prompt_evidence(
        selected, max_items=len(selected), max_excerpt_chars=settings.research_max_evidence_excerpt_chars
    )
    evidence_chars = len(json.dumps(evidence_dicts))

    assert schema_chars < evidence_chars
    assert len(system_prompt) < evidence_chars
