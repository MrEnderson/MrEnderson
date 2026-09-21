"""Shared fixture builders for v0.1.2.6 QA context compaction tests — not
a test module itself (no test_ functions here), imported by the actual
test files. Builds a realistic VALIDATION-shaped worker output dict
(matching what `ResearchOutput.model_dump(mode="json")` produces) shaped
like the live v0.1.2.5 benchmark: 3 candidates x 6 requirement categories,
with evidence/gaps that GROW across attempts — exactly the shape that
made the QA request explode 71,254 -> 110,274 -> 157,232 chars.
"""
from __future__ import annotations

import json

CANDIDATES = [
    ("candidate-ecommerce", "AI-Powered Content Personalization Platform for E-commerce"),
    ("candidate-compliance", "Compliance and Audit Documentation Automation SaaS"),
    ("candidate-bluecollar", "Niche Video Course Marketplace for Blue-Collar Skills"),
]
CATEGORIES = ("demand", "competition", "pricing", "customer_pain", "market_size", "feasibility")


def _evidence_dict(i: int, *, candidate_id: str, category: str, admitted: bool) -> dict:
    return {
        "id": f"e-{candidate_id}-{category}-{i}",
        "claim": f"Claim {i} about {category} for {candidate_id}: " + ("independent analysis detail. " * 6),
        "source_title": f"In-depth {category} analysis, source {i}",
        "source_url": f"https://www.example-vendor-{i}.com/reports/{category}/{i}?utm_source=search&ref=abc",
        "publisher": f"example-vendor-{i}.com",
        "published_at": None,
        "retrieved_at": "2026-09-18T00:00:00+00:00",
        "excerpt": ("According to the published methodology, this material covers the topic in detail. " * 4),
        "evidence_type": "OTHER",
        "confidence": 0.6,
        "query_used": f"{candidate_id} {category} query",
        "verification_status": "RETRIEVED",
        "source_quality": "AUTHORITATIVE" if i % 3 == 0 else "UNKNOWN",
        "evidence_depth": "PAGE_EXTRACT" if i % 2 == 0 else "SEARCH_SNIPPET",
        "candidate_id": candidate_id,
        "source_role": "COMMERCIAL_RESEARCH" if i % 3 == 0 else "UNKNOWN",
        "requirement_category": category,
        "relevance_score": 0.72,
        "relevance_label": "HIGH" if admitted else "MEDIUM",
        "rejection_reason": None,
        "research_task_id": "task-1",
        "research_mode": "VALIDATION",
        "attempt_number": 0,
        "admission_status": "ACCEPTED" if admitted else "REJECTED",
        "admission_rejection_reasons": [] if admitted else ["INSUFFICIENT_CANDIDATE_OVERLAP"],
    }


def _requirement_dict(candidate_id: str, category: str, status: str) -> dict:
    return {
        "id": f"req-{candidate_id}-{category}",
        "candidate_id": candidate_id,
        "category": category,
        "question": f"Detailed multi-clause question text about {category} for candidate {candidate_id}?",
        "importance": 4,
        "preferred_source_roles": ["PRIMARY", "MARKETPLACE", "AUTHORITATIVE"],
        "minimum_evidence_count": 2,
        "requires_independent_sources": True,
        "quantitative": True,
        "status": status,
    }


def _gap_dict(candidate_id: str, category: str, importance: int = 3) -> dict:
    return {
        "id": f"gap-{candidate_id}-{category}",
        "claim_or_question": f"Missing {category} evidence for {candidate_id}",
        "gap_type": category if category in ("market_size", "pricing", "demand") else "other",
        "importance": importance,
        "suggested_query": f"{candidate_id} {category} deep research query with extra detail words",
        "related_claim": None,
        "resolved": False,
        "supporting_evidence_ids": [],
        "candidate_id": candidate_id,
        "requirement_category": category,
    }


def realistic_output_for_attempt(attempt: int) -> dict:
    """Evidence and gap counts GROW with attempt number — accumulated
    across retries, exactly like the real evaluator.py loop's
    accumulated_evidence / accumulated_gaps."""
    n_evidence_per_cell = min(4, attempt + 1)  # accumulates, capped like real merge_evidence_items growth
    n_unresolved_categories = min(len(CATEGORIES), 2 + attempt)  # more cells still unresolved early on

    evidence = []
    requirements = []
    gaps = []
    for candidate_id, _label in CANDIDATES:
        for cat_index, category in enumerate(CATEGORIES):
            resolved_this_cell = cat_index >= n_unresolved_categories
            status = "SUFFICIENT" if resolved_this_cell else "MISSING"
            requirements.append(_requirement_dict(candidate_id, category, status))
            for i in range(n_evidence_per_cell):
                admitted = (i % 3 != 0)  # some rejected, mirroring live audit trail
                evidence.append(_evidence_dict(i, candidate_id=candidate_id, category=category, admitted=admitted))
            if not resolved_this_cell:
                gaps.append(_gap_dict(candidate_id, category, importance=5 - cat_index))

    return {
        "question": "Validate and compare candidate opportunities",
        "findings": [{"claim": f"Finding {i} with supporting detail text.", "evidence_type": "ASSUMPTION"} for i in range(5)],
        "evidence": evidence,
        "assumptions": [f"Assumption {i} about the mission." for i in range(3)],
        "unsupported_claims": [f"Unsupported claim {i} flagged for review." for i in range(2)],
        "open_questions": [f"Open question {i} still outstanding." for i in range(3)],
        "evidence_gaps": gaps,
        "insufficient_evidence": True,
        "summary": "Validation in progress across three candidates with partial coverage so far.",
        "requirements": requirements,
        "research_mode": "VALIDATION",
        "candidates": [{"id": cid, "label": label, "description": "", "discovery_evidence_ids": [], "status": "DISCOVERED"} for cid, label in CANDIDATES],
    }


def dump_chars(obj: dict) -> int:
    return len(json.dumps(obj))
