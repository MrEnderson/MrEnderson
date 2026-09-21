"""Model-facing Research DTOs (v0.1.2.1 grammar-size patch).

ARCHITECTURAL RULE: MODEL DTO != DOMAIN MODEL.

`app/schemas/agents.py::ResearchOutput` is Jarvis's rich INTERNAL/DOMAIN
contract — it carries `EvidenceItem`, `ResearchRequirement`,
`ResearchCandidate`, and other Research Intelligence structures that
`app/research_intelligence/` computes deterministically. Anthropic (or any
LLM) does not need to generate that whole contract — asking it to produces
a needlessly large compiled tool-call grammar (see docs/research_dto.md for
the measured root cause) and forces the model to reproduce metadata Jarvis
already owns, which invites hallucination of ids/statuses/scores it was
never asked to invent.

These DTOs are deliberately small — they carry ONLY the fields that
genuinely require model reasoning for each mode. Everything else (evidence,
candidate ids, requirements, source roles, relevance, coverage, gaps) is
attached to the rich `ResearchOutput` deterministically by
`app/agents/research.py` AFTER the model call returns. See
docs/research_intelligence.md, "Model DTO vs. Domain Model".
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class DiscoveryCandidateProposal(BaseModel):
    """A candidate opportunity the model is proposing — nothing else.
    `id`/`discovery_evidence_ids`/`status` are never part of this DTO; they
    are always recomputed deterministically by
    app/agents/research.py::_finalize_candidates, never trusted from the
    model."""

    label: str
    description: str = ""


class DiscoveryModelOutput(BaseModel):
    """DISCOVERY mode's entire model-facing contract. The model's only job
    is to identify candidates and report honestly on what it found — not to
    reproduce evidence, ids, or any other deterministic metadata."""

    candidates: list[DiscoveryCandidateProposal] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = False
    open_questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    summary: str = ""


class ValidationModelOutput(BaseModel):
    """VALIDATION mode's entire model-facing contract. Candidates, their
    ids, evidence, requirements, tagging, gaps, and coverage are ALL
    already owned by Jarvis by the time this is called — the model only
    reports findings/questions/assumptions over what was gathered."""

    findings: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = False
    open_questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    summary: str = ""


class GeneralResearchModelOutput(BaseModel):
    """GENERAL mode's model-facing contract — the unchanged v0.1.1/v0.1.2
    single-candidate research shape, minus the deterministic fields
    (evidence/requirements/research_mode/candidates/evidence_gaps) that
    app/agents/research.py already overwrites after every call regardless
    of what the model returns for them. `unsupported_claims` is kept
    (unlike Discovery/Validation) because the existing grounded system
    prompt genuinely relies on the model's own FACT-vs-unsupported-claim
    judgment, and app/security/evidence_qa.py reads it."""

    findings: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    insufficient_evidence: bool = False
    open_questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    summary: str = ""
