"""ResearchOutput must stay bounded across retries — deterministically, not
just via prompt wording — and the model-facing prompt must not grow without
bound either. Offline only; MockProvider/MockResearchProvider throughout."""
from __future__ import annotations

from app.agents.research import _bound_research_output, _prompt_evidence
from app.config.settings import get_settings
from app.orchestration.evaluator import _prioritized_evidence
from app.schemas.agents import ResearchFinding, ResearchOutput
from app.schemas.evidence import EvidenceGap, EvidenceItem


def _settings(**overrides):
    from app.config.settings import Settings

    base = dict(
        research_max_findings=12,
        research_max_evidence_items=15,
        research_max_open_questions=8,
        research_max_assumptions=8,
        research_max_gaps=8,
        research_max_finding_chars=1000,
        research_max_evidence_excerpt_chars=600,
    )
    base.update(overrides)
    return Settings(**base)


def _output(**overrides) -> ResearchOutput:
    base = dict(question="q", summary="s")
    base.update(overrides)
    return ResearchOutput(**base)


# --- 1-5: deterministic output bounding --------------------------------------


def test_findings_count_is_bounded():
    settings = _settings(research_max_findings=3)
    output = _output(
        findings=[
            ResearchFinding(claim=f"finding {i}", evidence_type="FACT") for i in range(10)
        ]
    )
    _bound_research_output(output, settings)
    assert len(output.findings) == 3


def test_open_questions_bounded():
    settings = _settings(research_max_open_questions=2)
    output = _output(open_questions=[f"q{i}" for i in range(10)])
    _bound_research_output(output, settings)
    assert len(output.open_questions) == 2


def test_assumptions_bounded():
    settings = _settings(research_max_assumptions=2)
    output = _output(assumptions=[f"a{i}" for i in range(10)])
    _bound_research_output(output, settings)
    assert len(output.assumptions) == 2


def test_evidence_gaps_bounded():
    settings = _settings(research_max_gaps=2)
    output = _output(
        evidence_gaps=[
            EvidenceGap(claim_or_question=f"gap {i}", gap_type="other") for i in range(10)
        ]
    )
    _bound_research_output(output, settings)
    assert len(output.evidence_gaps) == 2


def test_finding_claim_text_is_bounded():
    settings = _settings(research_max_finding_chars=20)
    long_claim = "x" * 500
    output = _output(findings=[ResearchFinding(claim=long_claim, evidence_type="FACT")])
    _bound_research_output(output, settings)
    assert len(output.findings[0].claim) <= 20 + len(" [truncated]")
    assert output.findings[0].claim.endswith("[truncated]")


def test_bounding_is_a_noop_when_already_within_limits():
    settings = _settings()
    output = _output(findings=[ResearchFinding(claim="short", evidence_type="FACT")])
    _bound_research_output(output, settings)
    assert len(output.findings) == 1
    assert output.findings[0].claim == "short"


# --- 6+8: prompt-facing evidence is compacted, bounded, and doesn't grow -----


def test_prompt_evidence_bounds_item_count():
    items = [EvidenceItem(claim=f"c{i}", source_url=f"https://example.com/{i}") for i in range(30)]
    prompt_items = _prompt_evidence(items, max_items=5, max_excerpt_chars=600)
    assert len(prompt_items) == 5


def test_prompt_evidence_bounds_excerpt_length():
    item = EvidenceItem(claim="c", source_url="https://example.com/a", excerpt="y" * 5000)
    prompt_items = _prompt_evidence([item], max_items=15, max_excerpt_chars=100)
    assert len(prompt_items[0]["excerpt"]) <= 100 + len(" [truncated]")


def test_prompt_evidence_never_grows_beyond_configured_bounds_regardless_of_input_size():
    """Simulates a retry where many more items than the bound were gathered —
    the prompt-facing payload must stay flat, not scale with input size."""
    small_batch = [EvidenceItem(claim=f"c{i}", source_url=f"https://example.com/{i}") for i in range(5)]
    large_batch = [EvidenceItem(claim=f"c{i}", source_url=f"https://example.com/{i}") for i in range(50)]

    small_prompt = _prompt_evidence(small_batch, max_items=10, max_excerpt_chars=600)
    large_prompt = _prompt_evidence(large_batch, max_items=10, max_excerpt_chars=600)

    assert len(small_prompt) == 5
    assert len(large_prompt) == 10  # capped, not 50


def test_prompt_evidence_prefers_page_extract_and_authoritative_first():
    weak = EvidenceItem(
        claim="weak", source_url="https://blog.example.com/a",
        evidence_depth="SEARCH_SNIPPET", source_quality="UNKNOWN",
    )
    strong = EvidenceItem(
        claim="strong", source_url="https://data.gov/b",
        evidence_depth="PAGE_EXTRACT", source_quality="AUTHORITATIVE",
    )
    prompt_items = _prompt_evidence([weak, strong], max_items=1, max_excerpt_chars=600)
    assert prompt_items[0]["claim"] == "strong"


# --- 7: PAGE_EXTRACT content is not blindly echoed ---------------------------


def test_grounded_prompt_instructs_against_echoing_page_extract():
    from app.agents.research import _grounded_system_prompt

    normalized = " ".join(_grounded_system_prompt(get_settings()).split()).lower()
    assert "do not echo full page_extract content" in normalized
    assert "cite the evidence id" in normalized or "reference it by evidence id" in normalized


def test_grounded_prompt_mentions_configured_bounds():
    settings = _settings(research_max_findings=7, research_max_finding_chars=250)
    prompt = _get_grounded_prompt(settings)
    assert "7" in prompt
    assert "250" in prompt


def _get_grounded_prompt(settings):
    from app.agents.research import _grounded_system_prompt

    return _grounded_system_prompt(settings)


# --- 10-11: evidence IDs stable, persisted evidence untouched by compaction -


def test_evidence_ids_remain_stable_through_prompt_compaction():
    item = EvidenceItem(claim="c", source_url="https://example.com/a", excerpt="y" * 5000)
    original_id = item.id
    prompt_items = _prompt_evidence([item], max_items=15, max_excerpt_chars=50)
    assert prompt_items[0]["id"] == original_id


def test_evidence_ids_remain_stable_through_output_prioritization():
    items = [EvidenceItem(claim=f"c{i}", source_url=f"https://example.com/{i}") for i in range(20)]
    original_ids = {i.id for i in items}
    bounded = _prioritized_evidence(items, max_items=5)
    assert len(bounded) == 5
    assert {i.id for i in bounded} <= original_ids


def test_prioritized_evidence_bounding_does_not_mutate_the_input_list():
    """Persisted evidence (the full accumulated list) must survive the
    output-facing cap untouched — the cap operates on a derived copy."""
    items = [EvidenceItem(claim=f"c{i}", source_url=f"https://example.com/{i}") for i in range(20)]
    original_length = len(items)
    _prioritized_evidence(items, max_items=5)
    assert len(items) == original_length  # untouched


def test_prioritized_evidence_is_a_noop_under_the_limit():
    items = [EvidenceItem(claim="c", source_url="https://example.com/a")]
    assert _prioritized_evidence(items, max_items=15) == items
