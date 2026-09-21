"""Agent-facing structured I/O schemas. All agent outputs must validate against these."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.database.models import PermissionLevel
from app.research_intelligence.schemas import CandidateResearchStatus, ResearchCandidate, ResearchRequirement
from app.schemas.evidence import EvidenceGap, EvidenceItem, ResearchMode

EvidenceType = Literal["FACT", "ASSUMPTION", "UNKNOWN"]


class AgentDescriptor(BaseModel):
    """A registry entry describing an available agent type."""

    name: str
    role: str
    description: str
    capabilities: list[str]
    permissions: list[PermissionLevel]
    model: str


class ResearchFinding(BaseModel):
    claim: str
    evidence_type: EvidenceType
    source: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)


class ResearchOutput(BaseModel):
    question: str
    findings: list[ResearchFinding] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(
        default_factory=list, description="Real, retrieved evidence backing FACT-labeled findings."
    )
    assumptions: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(
        default_factory=list, description="Claims that could not be traced to any EvidenceItem."
    )
    open_questions: list[str] = Field(default_factory=list)
    evidence_gaps: list[EvidenceGap] = Field(
        default_factory=list,
        description="Structured evidence gaps tracked across retries; see app/orchestration/evaluator.py.",
    )
    insufficient_evidence: bool = False
    summary: str
    requirements: list[ResearchRequirement] = Field(
        default_factory=list,
        description=(
            "This candidate's deterministic Research Requirement set (v0.1.2) with each "
            "requirement's .status reflecting its OWN gathered evidence — never model-generated, "
            "always overwritten deterministically after the model call. See "
            "app/research_intelligence/."
        ),
    )
    research_mode: ResearchMode = Field(
        default="GENERAL",
        description=(
            "Which mode this attempt actually ran under — always set deterministically by "
            "app/agents/research.py, never left to the model. See app/schemas/evidence.py."
        ),
    )
    candidates: list[ResearchCandidate] = Field(
        default_factory=list,
        description=(
            "DISCOVERY mode only: the candidate opportunities this task identified. The model "
            "proposes label/description; id/discovery_evidence_ids/status are always "
            "recomputed deterministically afterward. Empty outside DISCOVERY mode. See "
            "app/agents/research.py."
        ),
    )


class StrategyOption(BaseModel):
    name: str
    advantages: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)


class StrategyOutput(BaseModel):
    options_considered: list[StrategyOption] = Field(default_factory=list)
    recommendation: str
    reasoning: str
    assumptions: list[str] = Field(default_factory=list)
    evidence_used: list[str] = Field(
        default_factory=list,
        description="EvidenceItem ids from the research results that support this recommendation.",
    )
    unsupported_claims: list[str] = Field(
        default_factory=list,
        description="Quantitative or factual claims made without traceable supporting evidence.",
    )
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    comparison_ready: bool = Field(
        default=True,
        description=(
            "Deterministic Candidate Completeness Gate verdict (v0.1.2) — False means at least "
            "one candidate has not been researched to a comparable minimum standard. Always "
            "computed and overwritten deterministically after the model call, never "
            "model-generated. See app/research_intelligence/completeness.py."
        ),
    )
    candidate_statuses: list[CandidateResearchStatus] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    other_material_gaps: list[str] = Field(
        default_factory=list,
        description=(
            "v0.1.2.4 Defect 4: requirement gaps that are materially deficient but not "
            "CRITICAL — a non-critical category (market_size, feasibility, ...) sitting at "
            "MISSING, or a CRITICAL category (demand/competition/pricing) sitting at "
            "WEAK/PARTIAL rather than fully MISSING. Always computed and overwritten "
            "deterministically, never model-generated. See "
            "app/research_intelligence/completeness.py."
        ),
    )
    remediation_queries: list[str] = Field(
        default_factory=list,
        description="Bounded, prioritized follow-up search queries for the weakest coverage gaps (v0.1.2).",
    )


class ExecutionOutput(BaseModel):
    actions_performed: list[str] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    notes: str = ""
    blocked_on_approval: bool = False


class QAVerdict(BaseModel):
    verdict: Literal["PASS", "FAIL", "NEEDS_REVIEW"]
    score: float = Field(ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    feedback: str
