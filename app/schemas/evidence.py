"""Structured evidence model (v0.1.1/v0.1.3). An EvidenceItem is only ever
built from a real ResearchProvider result — never from model-invented text.
See app/agents/research.py::ResearchAgent._gather_evidence.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.database.models import EvidenceKind, EvidenceVerificationStatus

# Conservative, lightweight source classification. Never proves a claim is
# true — only describes what kind of source it came from. PRIMARY is never
# assigned automatically (see app/agents/research.py::classify_source_quality);
# it's reserved for a future, more confident signal.
SourceQuality = Literal["PRIMARY", "AUTHORITATIVE", "SECONDARY", "COMMUNITY", "UNKNOWN"]

# SEARCH_SNIPPET: built from a ResearchProvider.search() result only.
# PAGE_EXTRACT: the snippet was upgraded with real fetched page content via
# ResearchProvider.fetch() — see app/agents/research.py::_maybe_upgrade_with_fetch.
# Depth is provenance, not a truth score: PAGE_EXTRACT means "we retrieved
# deeper source material," never "this proves the claim."
EvidenceDepth = Literal["SEARCH_SNIPPET", "PAGE_EXTRACT"]

# Deliberately small taxonomy — see app/security/evidence_qa.py for where gaps
# of these types are detected, and docs on why it isn't larger.
EvidenceGapType = Literal[
    "market_size",
    "growth_rate",
    "competitor",
    "pricing",
    "demand",
    "customer_validation",
    "financial",
    "technical",
    "other",
]

# v0.1.2 Research Intelligence taxonomy — see app/research_intelligence/.
#
# SourceRole describes PROVENANCE/FUNCTION of a source, never truth quality —
# a PRIMARY source can still be biased, and a COMMUNITY source is not
# automatically weak (it is often the best evidence for customer pain). See
# app/research_intelligence/source_roles.py.
SourceRole = Literal[
    "PRIMARY",
    "AUTHORITATIVE",
    "COMMERCIAL_RESEARCH",
    "MARKETPLACE",
    "COMMUNITY",
    "DISCOVERY",
    "UNKNOWN",
]

# RelevanceLabel is a retrieval-relevance heuristic (query/requirement/
# candidate keyword overlap), never a probabilistic truth score. See
# app/research_intelligence/relevance.py.
RelevanceLabel = Literal["HIGH", "MEDIUM", "LOW", "REJECT"]

EvidenceRejectionReason = Literal[
    "IRRELEVANT_TOPIC",
    "TOO_GENERIC",
    "WRONG_CANDIDATE",
    "DOES_NOT_ADDRESS_REQUIREMENT",
]

# v0.1.2.4 Defect 3 — Evidence Admission Gate (see
# app/research_intelligence/admission.py). Distinct from relevance_label:
# relevance answers "how well does this match the requirement's keywords,"
# admission answers "should this be counted as authoritative validation
# evidence." An item can score MEDIUM relevance and still be REJECTED at
# admission (e.g. wrong-market authoritative source). ACCEPTED/REJECTED are
# only ever set for VALIDATION-mode items that actually went through the
# gate; NOT_EVALUATED covers everything else (DISCOVERY/GENERAL evidence,
# or VALIDATION evidence from before this gate existed) — never treated as
# accepted by default.
AdmissionStatus = Literal["ACCEPTED", "REJECTED", "NOT_EVALUATED"]

AdmissionRejectionReason = Literal[
    "NOT_VALIDATION_MODE",
    "NO_CANDIDATE_ID",
    "NO_REQUIREMENT_CATEGORY",
    "RELEVANCE_REJECTED",
    "BELOW_RELEVANCE_THRESHOLD",
    "INSUFFICIENT_CANDIDATE_OVERLAP",
    "SOURCE_UNSUITABLE_FOR_REQUIREMENT",
]

# What a piece of evidence could help establish. Reusable across business
# types (SaaS, ecommerce, services, marketplaces, ...) — never hard-codes a
# specific vertical. See app/research_intelligence/requirements.py.
RequirementCategory = Literal[
    "demand",
    "customer_pain",
    "competition",
    "pricing",
    "market_size",
    "growth",
    "willingness_to_pay",
    "feasibility",
    "unit_economics",
    "customer_validation",
    "other",
]

# v0.1.2.1 Discovery/Validation split (see app/research_intelligence/).
# DISCOVERY: candidates don't exist yet — Research is trying to find/name
# them. VALIDATION: candidates already exist (structured, from a prior
# discovery task) — Research is gathering candidate-specific evidence
# against a common requirement set. GENERAL: v0.1.1/v0.1.2 behavior,
# unchanged — a single implicit candidate = the task's own title. Always an
# explicit, structured field (set by the planner/executor) — never inferred
# from free-text keyword matching alone.
ResearchMode = Literal["DISCOVERY", "VALIDATION", "GENERAL"]


class EvidenceItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    claim: str
    source_title: str | None = None
    source_url: str | None = None
    publisher: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    excerpt: str | None = None
    evidence_type: EvidenceKind = EvidenceKind.OTHER
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    query_used: str | None = None
    verification_status: EvidenceVerificationStatus = EvidenceVerificationStatus.RETRIEVED
    source_quality: SourceQuality = "UNKNOWN"
    evidence_depth: EvidenceDepth = "SEARCH_SNIPPET"

    # v0.1.2 Research Intelligence fields — all deterministic, code-computed
    # (never model-generated), and all optional so every pre-existing
    # EvidenceItem/persisted Evidence row still validates unchanged. See
    # app/research_intelligence/.
    candidate_id: str | None = None
    source_role: SourceRole = "UNKNOWN"
    requirement_category: RequirementCategory | None = None
    relevance_score: float | None = Field(default=None, ge=0.0, le=1.0)
    relevance_label: RelevanceLabel | None = None
    rejection_reason: EvidenceRejectionReason | None = None

    # v0.1.2.3 evidence provenance (see docs/research_intelligence.md,
    # "Evidence provenance"). All optional/best-effort, all deterministic —
    # never model-generated. `query_used` above already serves as
    # "originating_query"; these three are the remaining traceability
    # fields: which research Task produced this item, under which mode,
    # and on which retry attempt. Used to stop evidence from a DISCOVERY
    # (or otherwise non-VALIDATION) task from ever being silently counted
    # toward VALIDATION coverage — see app/research_intelligence/gate.py.
    research_task_id: str | None = None
    research_mode: ResearchMode | None = None
    attempt_number: int | None = None

    # v0.1.2.4 Defect 3 — Evidence Admission Gate (see
    # app/research_intelligence/admission.py). Never deleted on rejection:
    # a REJECTED item keeps its reasons here for audit but must not count
    # toward coverage/completeness, enter Strategy's evidence context, be
    # cited as supporting evidence, appear in the report's main evidence
    # section, or consume retry model context.
    admission_status: AdmissionStatus = "NOT_EVALUATED"
    admission_rejection_reasons: list[AdmissionRejectionReason] = Field(default_factory=list)


class EvidenceGap(BaseModel):
    """A specific, structured hole in the evidence for a research task —
    what QA's evidence-quality checks identified as missing, turned into
    something a retry can act on (see app/orchestration/evaluator.py and
    app/agents/research.py::ResearchAgent._build_queries)."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    claim_or_question: str
    gap_type: EvidenceGapType = "other"
    importance: int = Field(ge=1, le=5, default=3)
    suggested_query: str | None = None
    related_claim: str | None = None
    resolved: bool = False
    supporting_evidence_ids: list[str] = Field(default_factory=list)

    # v0.1.2.5 Phase 7: which exact (candidate, requirement) cell this gap
    # targets — None for gap_types evidence_qa.py's own generic,
    # candidate-agnostic detector produces (GENERAL mode, or the
    # insufficient_evidence-driven text-mining check, which has no single
    # candidate to attribute to). When present (VALIDATION mode's own
    # app/research_intelligence per-cell gap generation — see
    # app/agents/research.py::_validation_gaps), this is what lets
    # app/orchestration/evaluator.py accumulate gaps for MULTIPLE
    # candidates sharing the same gap_type without one candidate's gap
    # silently overwriting another's.
    candidate_id: str | None = None
    requirement_category: RequirementCategory | None = None


def canonical_url(url: str | None) -> str | None:
    """Deterministic dedup key for a URL — not full RFC canonicalization,
    just enough to catch the common "same page, trivially different URL"
    cases (trailing slash, scheme/host case, fragment)."""
    if not url:
        return None
    parsed = urlparse(url.strip())
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme.lower()}://{netloc}{path}{('?' + parsed.query) if parsed.query else ''}"


def merge_evidence_items(existing: list[EvidenceItem], new: list[EvidenceItem]) -> list[EvidenceItem]:
    """Accumulates `new` onto `existing`, deduplicating by canonical URL (or,
    for URL-less items, by exact claim text) so a research retry adds to the
    evidence pool instead of replacing it, and never duplicates a source
    just because more than one query surfaced it. The first-seen item for a
    given key wins (and keeps its id) — later duplicates are dropped."""
    merged = list(existing)
    seen_urls = {canonical_url(e.source_url) for e in existing if e.source_url}
    seen_claims = {e.claim for e in existing if not e.source_url}

    for item in new:
        key = canonical_url(item.source_url)
        if key is not None:
            if key in seen_urls:
                continue
            seen_urls.add(key)
        else:
            if item.claim in seen_claims:
                continue
            seen_claims.add(item.claim)
        merged.append(item)

    return merged
