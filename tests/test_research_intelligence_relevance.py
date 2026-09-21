"""Evidence relevance scoring (Phase 5). Deterministic retrieval-relevance
heuristic, not a truth score. Offline."""
from __future__ import annotations

from app.research_intelligence.relevance import score_relevance
from app.research_intelligence.requirements import generate_requirement_set
from app.schemas.evidence import EvidenceItem

CANDIDATE = "Notion template marketplace"


def _requirement(category: str):
    reqs = generate_requirement_set(candidate_id="c", candidate_label=CANDIDATE, settings=_settings())
    return next(r for r in reqs if r.category == category)


def _settings():
    from app.config.settings import Settings

    return Settings()


def test_directly_relevant_evidence_scores_high():
    requirement = _requirement("demand")
    evidence = EvidenceItem(
        claim=f"{CANDIDATE} shows strong demand with growing traction and search volume on Product Hunt.",
        source_title=f"{CANDIDATE} trending on Product Hunt",
        source_url="https://www.producthunt.com/posts/x",
        excerpt=f"{CANDIDATE} demand and traction are increasing according to Product Hunt data.",
    )
    score, label, reason = score_relevance(requirement, CANDIDATE, evidence)
    assert label == "HIGH"
    assert reason is None
    assert score >= 0.75


def test_generic_category_level_material_scores_lower():
    requirement = _requirement("demand")
    evidence = EvidenceItem(
        claim="Top 10 best ways to make money online with digital products.",
        source_url="https://random-blog.example.com/top10",
    )
    score, label, reason = score_relevance(requirement, CANDIDATE, evidence)
    assert label in ("LOW", "REJECT")
    assert score < 0.5


def test_unrelated_result_is_rejected():
    requirement = _requirement("pricing")
    evidence = EvidenceItem(
        claim="A recipe for chocolate chip cookies with step-by-step instructions.",
        source_url="https://cooking.example.com/cookies",
    )
    score, label, reason = score_relevance(requirement, CANDIDATE, evidence)
    assert label == "REJECT"
    assert reason in ("IRRELEVANT_TOPIC", "DOES_NOT_ADDRESS_REQUIREMENT")


def test_wrong_candidate_evidence_is_rejected():
    requirement = _requirement("pricing")
    other_label = "Freelance pet sitting app"
    evidence = EvidenceItem(
        claim=f"{other_label} pricing plans start at $9 per booking, competitors charge similarly.",
        source_url="https://gumroad.com/l/pet-sitting",
    )
    score, label, reason = score_relevance(
        requirement, CANDIDATE, evidence, other_candidate_labels=[other_label]
    )
    assert label == "REJECT"
    assert reason == "WRONG_CANDIDATE"


def test_evidence_that_does_not_address_the_requirement_is_penalized():
    """Mentions the candidate but not the requirement's own category —
    should not score as highly as evidence addressing both."""
    requirement = _requirement("market_size")
    on_topic = EvidenceItem(
        claim=f"{CANDIDATE}: market size and total addressable market estimated by Statista.",
        source_url="https://www.statista.com/statistics/x",
    )
    off_topic = EvidenceItem(
        claim=f"{CANDIDATE} has a nice logo and clean design.",
        source_url="https://www.statista.com/statistics/x",
    )
    on_score, _, _ = score_relevance(requirement, CANDIDATE, on_topic)
    off_score, _, _ = score_relevance(requirement, CANDIDATE, off_topic)
    assert on_score > off_score
