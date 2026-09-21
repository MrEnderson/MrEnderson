"""v0.1.2.4 Defect 3: the Evidence Admission Gate.

    Tavily result -> EvidenceItem -> candidate/requirement tagging ->
    relevance + suitability -> EVIDENCE ADMISSION GATE
        |-- ACCEPT -> authoritative validation evidence
        `-- REJECT -> audit/rejected evidence only

Phase 5's cross-vertical negative tests, using the exact candidate names
from the checkpoint. Evidence is run through the REAL tagging pipeline
(tag_evidence_for_candidate -> score_relevance -> evaluate_admission), not
hand-set relevance_label/score fields, so these tests exercise the actual
call path, not a shortcut. Offline — no network call.
"""
from __future__ import annotations

from app.config.settings import Settings
from app.research_intelligence.admission import admitted_only, apply_admission_gate, evaluate_admission
from app.research_intelligence.requirements import generate_requirement_set
from app.research_intelligence.tagging import tag_evidence_for_candidate
from app.schemas.evidence import EvidenceItem

DASHBOARD_CANDIDATE = "Vertical-Specific Data & Analytics Dashboard"
CERTIFICATION_CANDIDATE = "Niche Professional Community & Certification Platform"
CONTENT_SUITE_CANDIDATE = "AI-Powered Content Creation Suite for Small Businesses"


def _settings() -> Settings:
    return Settings()


def _tag_for_market_size(candidate_label: str, evidence: EvidenceItem, settings: Settings) -> EvidenceItem:
    requirements = generate_requirement_set(candidate_id="c", candidate_label=candidate_label, settings=settings)
    tagged = tag_evidence_for_candidate(
        [evidence], candidate_id="c", candidate_label=candidate_label, requirements=requirements
    )
    return tagged[0]


def _validation_ready(item: EvidenceItem) -> EvidenceItem:
    """Admission rule 1 requires research_mode == VALIDATION (or None) —
    stamps what app/agents/research.py::_tag_research_provenance would
    have already stamped on a real VALIDATION-mode item."""
    return item.model_copy(update={"research_mode": "VALIDATION"})


def test_hr_candidate_experience_evidence_rejected_for_analytics_dashboard_market_size():
    """The exact reported bug: an authoritative HR "candidate skills
    assessment market" / "candidate experience statistics" page scores
    non-trivial relevance for a data-analytics-dashboard candidate's
    market_size requirement purely on the "market size" keyword hit — but
    shares ZERO topical tokens with the candidate itself. The admission
    gate's candidate-overlap rule (Phase 4 rule 6) must reject it."""
    settings = _settings()
    hr_evidence = EvidenceItem(
        claim=(
            "The candidate skills assessment market size was estimated using vendor revenue "
            "disclosures and independent analyst estimates."
        ),
        source_title="Candidate Skills Assessment: Market Size Report",
        source_url="https://www.grandviewresearch.com/industry-analysis/candidate-assessment-market",
        excerpt=(
            "This report values the global candidate skills assessment market size based on "
            "vendor revenue disclosures."
        ),
    )
    tagged = _validation_ready(_tag_for_market_size(DASHBOARD_CANDIDATE, hr_evidence, settings))
    assert tagged.requirement_category == "market_size"
    assert tagged.relevance_label != "REJECT"  # confirms this is the MEDIUM-relevance leak, not a trivial REJECT

    accepted, reasons = evaluate_admission(
        tagged, candidate_label=DASHBOARD_CANDIDATE, candidate_description="", settings=settings
    )
    assert accepted is False
    assert "INSUFFICIENT_CANDIDATE_OVERLAP" in reasons


def test_candidate_skills_market_evidence_rejected_for_certification_platform_market_size():
    """Generic professional certification is discovery-adjacent for this
    candidate, but HR candidate-assessment MARKET-SIZE data must not
    satisfy ITS market_size requirement either — different topic
    entirely, however well the "market size" keyword matches."""
    settings = _settings()
    hr_market_evidence = EvidenceItem(
        claim=(
            "Candidate skills assessment and pre-employment testing market size to reach 5 "
            "billion dollars by 2030."
        ),
        source_title="HR Tech Market Report: Candidate Assessment Industry",
        source_url="https://www.marketsandmarkets.com/candidate-assessment-market",
        excerpt="Market sizing for candidate skills assessment vendors based on recruiting technology spend.",
    )
    tagged = _validation_ready(_tag_for_market_size(CERTIFICATION_CANDIDATE, hr_market_evidence, settings))
    accepted, reasons = evaluate_admission(
        tagged, candidate_label=CERTIFICATION_CANDIDATE, candidate_description="", settings=settings
    )
    assert accepted is False
    assert "INSUFFICIENT_CANDIDATE_OVERLAP" in reasons


def test_jasper_pricing_evidence_admitted_for_ai_content_suite_when_tagged_as_pricing():
    """Jasper/Copy.ai pricing evidence properly tagged as a `pricing`
    requirement for the AI content-creation candidate SHOULD be admitted —
    the gate must not become so strict it rejects genuinely on-topic
    competitor-pricing evidence."""
    settings = _settings()
    jasper_pricing = EvidenceItem(
        claim=(
            "Jasper AI content generation pricing starts at 49 dollars per month for the "
            "Creator plan; Copy.ai starts at 49 dollars per month too."
        ),
        source_title="Jasper AI Pricing Plans",
        source_url="https://www.jasper.ai/pricing",
        excerpt=(
            "Jasper AI-powered content creation plans for small business content marketing "
            "start at 49 dollars per month."
        ),
    )
    tagged = _validation_ready(_tag_for_market_size(CONTENT_SUITE_CANDIDATE, jasper_pricing, settings))
    assert tagged.requirement_category == "pricing"

    accepted, reasons = evaluate_admission(
        tagged, candidate_label=CONTENT_SUITE_CANDIDATE, candidate_description="", settings=settings
    )
    assert accepted is True, f"expected ACCEPT, got rejection reasons: {reasons}"


def test_wrong_market_authoritative_commercial_research_source_still_rejected():
    """Phase 6: source authority is not topic relevance. An AUTHORITATIVE/
    COMMERCIAL_RESEARCH-classified source about the WRONG market must still
    be rejected — suitability alone (rule 7) never overrides a failed
    candidate-overlap check (rule 6)."""
    settings = _settings()
    wrong_market_authoritative = EvidenceItem(
        claim="Global background screening industry market size valued at 6 billion dollars.",
        source_title="Statista: Background Screening Industry Market Size",
        source_url="https://www.statista.com/statistics/background-screening-market-size",
        excerpt="Statista market research on the background screening and pre-employment vetting industry size.",
    )
    tagged = _validation_ready(_tag_for_market_size(DASHBOARD_CANDIDATE, wrong_market_authoritative, settings))
    assert tagged.source_role == "COMMERCIAL_RESEARCH"  # confirms it WOULD look authoritative

    accepted, reasons = evaluate_admission(
        tagged, candidate_label=DASHBOARD_CANDIDATE, candidate_description="", settings=settings
    )
    assert accepted is False
    assert "INSUFFICIENT_CANDIDATE_OVERLAP" in reasons


def test_source_suitability_alone_cannot_override_poor_topical_relevance():
    """A STRONG-suitability source role for a requirement category
    (market_size -> COMMERCIAL_RESEARCH is STRONG per suitability.py) must
    not, by itself, admit an off-topic item — suitability and relevance
    are independent gates, both must pass."""
    settings = _settings()
    item = EvidenceItem(
        claim="Irrelevant off-topic market size figures for a completely unrelated business sector.",
        source_url="https://www.gartner.com/some-unrelated-market-report",
        source_role="COMMERCIAL_RESEARCH",
        requirement_category="market_size",
        relevance_label="MEDIUM",
        relevance_score=0.55,
        candidate_id="c",
        research_mode="VALIDATION",
    )
    accepted, reasons = evaluate_admission(
        item, candidate_label=DASHBOARD_CANDIDATE, candidate_description="", settings=settings
    )
    assert accepted is False
    assert "INSUFFICIENT_CANDIDATE_OVERLAP" in reasons


def test_rejected_evidence_excluded_from_coverage_and_admitted_only():
    """REJECT evidence is available for audit (stays in the returned list,
    admission_status=REJECTED, reasons kept) but admitted_only() — the one
    filter every downstream consumer must use — excludes it."""
    settings = _settings()
    hr_evidence = EvidenceItem(
        claim="Candidate skills assessment market size estimated at 3.2 billion dollars.",
        source_url="https://www.grandviewresearch.com/candidate-assessment-market",
        excerpt="Candidate skills assessment market sizing report based on vendor revenue disclosures.",
    )
    good_evidence = EvidenceItem(
        claim=f"{DASHBOARD_CANDIDATE} addressable market sized using vendor revenue disclosures.",
        source_url="https://www.gartner.com/data-analytics-dashboard-market",
        excerpt=f"Analyst estimate of the {DASHBOARD_CANDIDATE} market size and growth trajectory.",
    )
    settings_reqs = generate_requirement_set(candidate_id="c", candidate_label=DASHBOARD_CANDIDATE, settings=settings)
    tagged = tag_evidence_for_candidate(
        [hr_evidence, good_evidence], candidate_id="c", candidate_label=DASHBOARD_CANDIDATE, requirements=settings_reqs
    )
    tagged = [_validation_ready(t) for t in tagged]

    stamped = apply_admission_gate(
        tagged, candidates_by_id={"c": (DASHBOARD_CANDIDATE, "")}, settings=settings
    )
    assert len(stamped) == 2  # nothing dropped/deleted
    rejected = [i for i in stamped if i.admission_status == "REJECTED"]
    accepted = [i for i in stamped if i.admission_status == "ACCEPTED"]
    assert len(rejected) == 1 and rejected[0].claim.startswith("Candidate skills assessment")
    assert len(accepted) == 1

    only = admitted_only(stamped)
    assert len(only) == 1
    assert only[0].admission_status == "ACCEPTED"
    # Audit trail preserved — the rejected item is still IN `stamped`,
    # just not in admitted_only()'s output.
    assert any(i.admission_status == "REJECTED" for i in stamped)


def test_admission_gate_rejects_evidence_with_no_candidate_id_or_requirement_category():
    """Rules 2/3: an item that was never successfully tagged (no
    candidate_id, no requirement_category) can never be admitted, no
    matter what its relevance score happens to be."""
    settings = _settings()
    untagged = EvidenceItem(claim="Some claim.", relevance_label="HIGH", relevance_score=0.9)
    accepted, reasons = evaluate_admission(
        untagged, candidate_label=DASHBOARD_CANDIDATE, candidate_description="", settings=settings
    )
    assert accepted is False
    assert "NO_CANDIDATE_ID" in reasons
    assert "NO_REQUIREMENT_CATEGORY" in reasons


def test_gate_py_excludes_rejected_evidence_from_comparison_readiness():
    """End-to-end through app/research_intelligence/gate.py::
    evaluate_comparison_readiness (Strategy's own independent
    re-verification path, not just research.py's) — off-topic HR evidence
    tagged for the analytics-dashboard candidate must not inflate its
    market_size coverage, even though it would have passed the OLDER
    relevance-only check (MEDIUM, not REJECT)."""
    import uuid

    from app.research_intelligence.gate import evaluate_comparison_readiness

    def _item(url: str, claim: str, **overrides) -> dict:
        base = {"id": str(uuid.uuid4()), "claim": claim, "source_url": url, "excerpt": claim, "research_mode": "VALIDATION"}
        base.update(overrides)
        return base

    off_topic_hr = _item(
        "https://www.grandviewresearch.com/industry-analysis/candidate-assessment-market",
        "The candidate skills assessment market size was estimated using vendor revenue disclosures and independent analyst estimates.",
    )
    other_candidate_evidence = [
        _item(f"https://www.gartner.com/reports/other-{i}", f"Other Candidate: market size and total addressable market estimate {i}.")
        for i in range(2)
    ]
    research_results = [
        {
            "task_id": "validation-1",
            "title": "validation-1",
            "question": "validation-1",
            "evidence": [off_topic_hr] + other_candidate_evidence,
            "candidates": [{"label": DASHBOARD_CANDIDATE}, {"label": "Other Candidate"}],
        }
    ]
    readiness = evaluate_comparison_readiness(research_results, settings=_settings())
    statuses = {s.candidate_label: s for s in readiness.candidate_statuses}
    assert statuses[DASHBOARD_CANDIDATE].coverage_percentage == 0.0
    assert "market_size" in statuses[DASHBOARD_CANDIDATE].critical_requirements_missing + statuses[DASHBOARD_CANDIDATE].other_material_gaps


async def test_rejected_evidence_never_reaches_the_research_model_prompt():
    """End-to-end through ResearchAgent._run_validation: off-topic HR
    evidence must not consume retry/prompt model context — the model
    prompt the provider actually receives must not contain its claim
    text, while a genuinely on-topic item's claim text IS present."""
    from app.agents.research import ResearchAgent
    from app.database.models import PermissionLevel
    from app.schemas.agents import AgentDescriptor
    from app.schemas.research_dto import ValidationModelOutput
    from app.tools.research_tools import SearchResult

    off_topic_claim = "The candidate skills assessment market size was estimated using vendor revenue disclosures."
    on_topic_claim = f"{DASHBOARD_CANDIDATE} addressable market sized using vendor revenue disclosures."

    class _Provider:
        name = "fake"
        is_live = True

        async def search(self, query, *, max_results=5):
            return [
                SearchResult(
                    title="Candidate Skills Assessment: Market Size Report",
                    url="https://www.grandviewresearch.com/industry-analysis/candidate-assessment-market",
                    snippet=off_topic_claim,
                ),
                SearchResult(
                    title="Analyst Market Report",
                    url="https://www.gartner.com/data-analytics-dashboard-market",
                    snippet=on_topic_claim,
                ),
            ]

        async def fetch(self, url):
            raise NotImplementedError

        async def extract(self, content, question):
            raise NotImplementedError

    captured_prompts: list[str] = []

    class _Model:
        name = "stub"

        async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
            captured_prompts.append(user_prompt)
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
            "candidates": [{"id": "a", "label": DASHBOARD_CANDIDATE}],
            "task_id": "task-1",
            "attempt_number": 0,
        },
        context={},
    )
    assert captured_prompts, "provider was never called"
    prompt = captured_prompts[0]
    admitted_ids = {e.id for e in result.evidence if e.admission_status == "ACCEPTED"}
    rejected_ids = {e.id for e in result.evidence if e.admission_status == "REJECTED"}
    assert admitted_ids and rejected_ids, "expected both an accepted and a rejected item"
    for rejected_id in rejected_ids:
        assert rejected_id not in prompt
    # Audit trail: the rejected item still survives on the persisted output.
    assert any(e.admission_status == "REJECTED" for e in result.evidence)


def test_admission_gate_rejects_non_validation_research_mode():
    """Rule 1: DISCOVERY-mode evidence must never be admitted as
    authoritative VALIDATION evidence, even if perfectly tagged/relevant."""
    settings = _settings()
    discovery_item = EvidenceItem(
        claim=f"{DASHBOARD_CANDIDATE} pricing information.",
        candidate_id="c",
        requirement_category="pricing",
        relevance_label="HIGH",
        relevance_score=0.9,
        research_mode="DISCOVERY",
        source_role="PRIMARY",
    )
    accepted, reasons = evaluate_admission(
        discovery_item, candidate_label=DASHBOARD_CANDIDATE, candidate_description="", settings=settings
    )
    assert accepted is False
    assert "NOT_VALIDATION_MODE" in reasons
