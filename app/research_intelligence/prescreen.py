"""Negative retrieval guards + pre-extraction admission screen (v0.1.2.5
Phases 5/6).

    SEARCH RESULT -> PRE-SCREEN -> optional PAGE_EXTRACT -> EvidenceItem
        -> ADMISSION GATE -> authoritative evidence

Pre-screen is a CHEAP, CONSERVATIVE, cost-saving filter applied to a raw
`SearchResult` BEFORE it is ever turned into an `EvidenceItem` (never
after) — it exists so a Tavily PAGE_EXTRACT call, and the rest of the
tagging/relevance/admission pipeline, is never spent on a result that is
obviously noise for this research context (the live v0.1.2.4 benchmark
kept retrieving HR/ATS material for digital-product validation). It is
NOT a correctness gate and never replaces
app/research_intelligence/admission.py, which remains the only thing that
decides ACCEPT/REJECT for authoritative validation evidence — a result
that survives pre-screen can still be rejected there.

The guard is never a global ban on a word. "jobs"/"recruiting"/
"applicant"/"candidate assessment"/"political candidate"/"election" are
excluded only when the CANDIDATE ITSELF being researched doesn't already
legitimately relate to that domain (e.g. a recruiting-software or
civic-tech candidate needs exactly this vocabulary in its own evidence).
"""
from __future__ import annotations

from app.tools.research_tools import SearchResult

# marker phrase -> noise category. Deliberately small and explicit, not a
# general profanity/topic classifier — see module docstring.
_NOISE_CATEGORY_MARKERS: dict[str, tuple[str, ...]] = {
    "hr_recruiting": (
        "job posting",
        "job openings",
        "recruitment",
        "recruiting",
        "applicant tracking",
        "applicant",
        "candidate assessment",
        "candidate screening",
        "candidate experience",
        "background screening",
        "background check",
        "hiring manager",
        "resume screening",
        "cv screening",
    ),
    "political": (
        "political candidate",
        "election",
        "ballot",
        "campaign donation",
        "voter turnout",
        "primary election",
    ),
}

# A candidate whose OWN concept set contains one of these tokens is
# genuinely about that noise category — the guard must not fire for it.
_CATEGORY_RELATED_CONCEPT_TOKENS: dict[str, tuple[str, ...]] = {
    "hr_recruiting": ("recruit", "hiring", "applicant", "staffing", "job board", "talent acquisition", "hr "),
    "political": ("election", "campaign", "civic", "voter", "political"),
}


def _candidate_relates_to_category(concepts: list[str], category: str) -> bool:
    tokens = _CATEGORY_RELATED_CONCEPT_TOKENS.get(category, ())
    combined = " ".join(concepts).lower()
    return any(token in combined for token in tokens)


def negative_terms_for_candidate(concepts: list[str]) -> list[str]:
    """Bounded set of noise markers to treat as exclusion signals for THIS
    candidate — every noise category the candidate's own concepts don't
    already legitimately relate to (Phase 4/5's `excluded_terms`)."""
    terms: list[str] = []
    for category, markers in _NOISE_CATEGORY_MARKERS.items():
        if _candidate_relates_to_category(concepts, category):
            continue
        terms.extend(markers)
    return terms


def _text_of(result: SearchResult) -> str:
    return " ".join(filter(None, [result.title, result.snippet])).lower()


def is_contextually_excluded(result: SearchResult, *, concepts: list[str]) -> bool:
    """True if `result` looks like noise from a category the candidate's
    own concepts don't relate to. Conservative: fires only on an exact
    marker-phrase substring match, never a fuzzy heuristic."""
    text = _text_of(result)
    for category, markers in _NOISE_CATEGORY_MARKERS.items():
        if _candidate_relates_to_category(concepts, category):
            continue
        if any(marker in text for marker in markers):
            return True
    return False


def prescreen_search_result(result: SearchResult, *, concepts: list[str]) -> bool:
    """Returns True (plausible — proceed to EvidenceItem/possible
    PAGE_EXTRACT) unless `result` is contextually-excluded noise. This is
    the ONLY function app/agents/research.py should call for pre-screen —
    never re-derive the marker lists elsewhere."""
    return not is_contextually_excluded(result, concepts=concepts)
