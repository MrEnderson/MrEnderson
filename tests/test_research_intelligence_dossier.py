"""Research Dossier (Phase 10): deterministically constructed from data
already computed elsewhere in the pipeline — never asks a model to
reproduce it. Offline."""
from __future__ import annotations

from app.research_intelligence.completeness import evaluate_completeness
from app.research_intelligence.coverage import build_coverage_matrix
from app.research_intelligence.dossier import build_research_dossier
from app.research_intelligence.requirements import generate_requirement_set
from app.research_intelligence.tagging import tag_evidence_for_candidate
from app.config.settings import Settings
from app.schemas.evidence import EvidenceItem


def test_dossier_reflects_coverage_and_readiness():
    settings = Settings()
    candidates = {
        "cand-a": ("Notion template marketplace", [
            EvidenceItem(
                claim="Notion template marketplace: strong demand and growing traction on Product Hunt.",
                source_url="https://www.producthunt.com/posts/x",
            ),
            EvidenceItem(
                claim="Similarweb data shows strong demand and traction for Notion template marketplace.",
                source_url="https://www.similarweb.com/website/x",
            ),
        ]),
        "cand-b": ("Coda template hub", [
            EvidenceItem(
                claim="Top 10 best ways to make money online with digital products.",
                source_url="https://random-blog.example.com/top10",
            ),
        ]),
    }

    requirements = []
    evidence_by_candidate = {}
    labels = {}
    for cid, (label, items) in candidates.items():
        labels[cid] = label
        reqs = generate_requirement_set(candidate_id=cid, candidate_label=label, settings=settings)
        requirements.extend(reqs)
        evidence_by_candidate[cid] = tag_evidence_for_candidate(
            items, candidate_id=cid, candidate_label=label, requirements=reqs
        )

    cells = build_coverage_matrix(requirements, evidence_by_candidate, settings=settings)
    readiness = evaluate_completeness(requirements, cells, labels, settings=settings)

    dossier = build_research_dossier(
        objective="Find the strongest opportunity",
        requirements=requirements,
        coverage_cells=cells,
        comparison_readiness=readiness,
        candidate_labels=labels,
    )

    assert dossier.comparison_readiness.ready is False
    assert set(dossier.candidates) == {"Notion template marketplace", "Coda template hub"}
    entry_by_label = {e.candidate_label: e for e in dossier.candidate_entries}
    assert entry_by_label["Notion template marketplace"].confidence in ("HIGH", "MEDIUM")
    assert entry_by_label["Coda template hub"].missing_evidence
    assert dossier.unresolved_gaps

    text = dossier.to_text()
    assert "COMPARISON READINESS: NOT READY" in text
    assert "Notion template marketplace" in text
