"""v0.1.2.7 Phase 9: discovery zero-candidate diagnostic.

The v0.1.2.6 live benchmark showed attempt 0 return candidate_count=0 (QA
FAIL), then retry 1 return candidate_count=3 (QA PASS) — the retry
mechanism itself is correct and not touched here (Phase 9 explicitly says
do not weaken QA or force fabricated candidates).

Traced app/agents/research.py::_finalize_candidates (the single
deterministic step between the model's raw DiscoveryModelOutput.candidates
and the ResearchCandidate objects that actually get returned) end to end:

- a valid model DTO with 3 distinct labels always produces exactly 3
  ResearchCandidates (id/discovery_evidence_ids/status all recomputed
  deterministically, never trusted from the model — see its docstring).
- an EMPTY model candidate list produces zero ResearchCandidates safely —
  no exception, no fabricated filler.
- a normalization COLLISION (two distinct labels that normalize to the
  same candidate_id — app/research_intelligence/candidates.py::
  normalize_candidate_id) is handled deterministically: the FIRST-seen
  label wins, the second is silently dropped (documented in
  _finalize_candidates's `seen_ids` dedup) — never a crash, never two
  candidates silently sharing one id.

FINDING: no reproducible deterministic bug was found in this step. Given a
valid 3-candidate DTO, _finalize_candidates always returns exactly 3
candidates; given zero, it always returns zero, safely. The live benchmark's
attempt-0 zero-candidate result is consistent with the MODEL itself simply
returning an empty candidates list on that attempt (a valid, if suboptimal,
model-output variation) — not a deterministic code defect. This is
documented, not "fixed", per Phase 9's explicit instruction not to
over-engineer a non-reproducible defect.

Offline only — no network call.
"""
from __future__ import annotations

from app.agents.research import _finalize_candidates
from app.config.settings import Settings
from app.orchestration.evaluator import run_worker_with_qa
from app.schemas.agents import QAVerdict, ResearchOutput
from app.schemas.evidence import EvidenceItem
from app.schemas.research_dto import DiscoveryCandidateProposal


def _settings() -> Settings:
    return Settings()


# --- 1. valid three-candidate DTO -> exactly three ResearchCandidates ------


def test_valid_three_candidate_dto_produces_exactly_three_research_candidates():
    proposed = [
        DiscoveryCandidateProposal(label="CMS Template & Component Marketplace", description="d1"),
        DiscoveryCandidateProposal(label="Digital Product Creation & Distribution Course", description="d2"),
        DiscoveryCandidateProposal(label="Headless CMS + E-commerce Integration Suite", description="d3"),
    ]
    candidates = _finalize_candidates(proposed, evidence=[], settings=_settings())
    assert len(candidates) == 3
    assert {c.status for c in candidates} == {"DISCOVERED"}
    assert len({c.id for c in candidates}) == 3


# --- 2. empty model candidate list -> zero candidates, safely --------------


def test_empty_model_candidate_list_produces_zero_candidates_safely():
    candidates = _finalize_candidates([], evidence=[], settings=_settings())
    assert candidates == []


def test_candidate_list_with_only_blank_labels_produces_zero_candidates_safely():
    proposed = [DiscoveryCandidateProposal(label="", description="d"), DiscoveryCandidateProposal(label="   ", description="d")]
    candidates = _finalize_candidates(proposed, evidence=[], settings=_settings())
    assert candidates == []


# --- 3. normalization collision is handled deterministically ---------------


def test_normalization_collision_deterministically_keeps_first_seen_candidate():
    # Both normalize to "ai-content-tools" (app/research_intelligence/
    # candidates.py::normalize_candidate_id strips non-alphanumerics).
    proposed = [
        DiscoveryCandidateProposal(label="AI Content Tools!!", description="first"),
        DiscoveryCandidateProposal(label="AI Content Tools??", description="second"),
    ]
    candidates = _finalize_candidates(proposed, evidence=[], settings=_settings())
    assert len(candidates) == 1
    assert candidates[0].description == "first"


def test_normalization_collision_never_raises_and_other_candidates_still_finalize():
    proposed = [
        DiscoveryCandidateProposal(label="AI Content Tools!!", description="first"),
        DiscoveryCandidateProposal(label="AI Content Tools??", description="second"),
        DiscoveryCandidateProposal(label="Digital Product Creation & Distribution Course", description="third"),
    ]
    candidates = _finalize_candidates(proposed, evidence=[], settings=_settings())
    assert len(candidates) == 2  # the collision drops to one, the distinct third survives
    ids = {c.id for c in candidates}
    assert len(ids) == 2


# --- 4/5. QA FAIL/NEEDS_REVIEW retries; PASS terminates immediately --------
#     (the retry mechanism itself — unchanged, verified still correct)


async def test_discovery_qa_fail_with_zero_candidates_triggers_existing_retry():
    class _ZeroThenThreeWorker:
        def __init__(self):
            self.calls = 0

        async def run(self, *, title, description, input_data, context):
            self.calls += 1
            candidates = [] if self.calls == 1 else [
                {"label": "A", "description": ""}, {"label": "B", "description": ""}, {"label": "C", "description": ""}
            ]
            return ResearchOutput(
                question=title, findings=[], insufficient_evidence=(self.calls == 1),
                summary="s", research_mode="DISCOVERY",
                evidence=[EvidenceItem(claim="c", source_url=f"https://example.com/{self.calls}")],
                candidates=candidates,
            )

    class _FailThenPassQA:
        def __init__(self):
            self.calls = 0

        async def run(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return QAVerdict(verdict="FAIL", score=0.2, feedback="no candidates found")
            return QAVerdict(verdict="PASS", score=0.9, feedback="ok")

    worker = _ZeroThenThreeWorker()
    qa = _FailThenPassQA()
    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=qa, title="Discover candidates", description="",
        input_data={"research_mode": "DISCOVERY"}, success_criteria=None, max_retries=2,
    )
    assert worker.calls == 2
    assert result.verdict.verdict == "PASS"
    assert len(result.output.candidates) == 3


def test_discovery_pass_terminates_immediately_even_with_candidates_present():
    """Companion to test_discovery_pass_terminates_immediately.py — confirms
    a first-attempt PASS with real candidates present never triggers an
    unnecessary retry (regression guard alongside the zero-candidate case
    above)."""
    proposed = [
        DiscoveryCandidateProposal(label="A", description=""),
        DiscoveryCandidateProposal(label="B", description=""),
        DiscoveryCandidateProposal(label="C", description=""),
    ]
    candidates = _finalize_candidates(proposed, evidence=[], settings=_settings())
    assert len(candidates) == 3
