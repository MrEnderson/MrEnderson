"""Structured types for the Research Intelligence pipeline. All deterministic,
code-constructed — never model-generated (see app/research_intelligence/__init__.py).
"""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.evidence import RequirementCategory, SourceRole

SuitabilityLevel = Literal["STRONG", "ACCEPTABLE", "WEAK", "UNSUITABLE"]

CoverageStatus = Literal["MISSING", "WEAK", "PARTIAL", "SUFFICIENT"]


class ResearchQueryPlan(BaseModel):
    """v0.1.2.5 Phase 2: the deterministic, structured plan behind every
    external search query this pipeline issues — built from CANDIDATE
    CONCEPT + REQUIREMENT-SPECIFIC INTENT, never from Jarvis's own
    task/orchestration wording. See app/research_intelligence/
    query_builder.py::build_query_plan, the single place every
    query-generating call site (initial validation search, gap retries)
    should go through."""

    candidate_id: str
    candidate_label: str
    candidate_concept: str
    requirement_category: RequirementCategory | None = None
    search_intent: str
    query: str
    preferred_source_roles: list[SourceRole] = Field(default_factory=list)
    excluded_terms: list[str] = Field(default_factory=list)
    max_results: int


class ResearchCandidate(BaseModel):
    """A candidate opportunity identified by a DISCOVERY-mode research task
    (or carried into a VALIDATION-mode one). Discovery evidence establishes
    that a candidate is worth investigating — it never, by itself, means the
    candidate has been VALIDATED; see app/research_intelligence/gate.py and
    app/agents/research.py."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    label: str
    description: str = ""
    discovery_evidence_ids: list[str] = Field(default_factory=list)
    status: str = "DISCOVERED"


class ResearchRequirement(BaseModel):
    """A single, specific thing that must be established before a candidate
    can be trusted for comparison — see app/research_intelligence/requirements.py.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    candidate_id: str | None = None
    category: RequirementCategory
    question: str
    importance: int = Field(ge=1, le=5, default=3)
    preferred_source_roles: list[SourceRole] = Field(default_factory=list)
    minimum_evidence_count: int = 2
    requires_independent_sources: bool = True
    quantitative: bool = False
    status: CoverageStatus = "MISSING"


class CoverageCell(BaseModel):
    """One (candidate, requirement) cell of the coverage matrix — see
    app/research_intelligence/coverage.py."""

    requirement_id: str
    candidate_id: str
    category: RequirementCategory
    evidence_ids: list[str] = Field(default_factory=list)
    strong_count: int = 0
    acceptable_count: int = 0
    weak_count: int = 0
    independent_domain_count: int = 0
    best_evidence_depth: str | None = None
    status: CoverageStatus = "MISSING"


class CandidateResearchStatus(BaseModel):
    """Per-candidate rollup of coverage across its requirement set — see
    app/research_intelligence/completeness.py."""

    candidate_id: str
    candidate_label: str
    coverage_percentage: float = 0.0
    critical_requirements_missing: list[str] = Field(default_factory=list)
    # v0.1.2.4 Defect 4: every requirement category NOT at SUFFICIENT status
    # that isn't already in critical_requirements_missing lands here — a
    # non-critical category (market_size, feasibility, ...) sitting at
    # MISSING, or a CRITICAL category sitting at WEAK/PARTIAL rather than
    # fully MISSING. Named for what the report shows it as ("OTHER MATERIAL
    # GAPS"), replacing the old, narrower `weak_requirements` (which only
    # ever caught WEAK/PARTIAL, silently dropping a non-critical MISSING
    # category). See app/research_intelligence/completeness.py.
    other_material_gaps: list[str] = Field(default_factory=list)
    ready_for_comparison: bool = False


class ComparisonReadiness(BaseModel):
    """Whether Strategy is allowed to rank candidates against each other —
    see app/research_intelligence/completeness.py and
    app/agents/strategy.py."""

    ready: bool = False
    candidate_statuses: list[CandidateResearchStatus] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    other_material_gaps: list[str] = Field(default_factory=list)
    remediation_queries: list[str] = Field(default_factory=list)
