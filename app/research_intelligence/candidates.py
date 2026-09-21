"""Deterministic candidate identity. A "candidate" in this pipeline is
whatever a research task's own `title` names — this architecture is not
redesigned to add an explicit Candidate entity; each research task in a
comparison objective is treated as one candidate (see
app/agents/research.py and app/agents/strategy.py)."""
from __future__ import annotations

import re


def normalize_candidate_id(label: str | None) -> str:
    """Stable, deterministic slug used as candidate_id everywhere in this
    package — the SAME normalization is applied wherever a candidate_id is
    derived from a title, so research.py's own tagging and strategy.py's
    cross-candidate coverage always agree on identity."""
    if not label:
        return "candidate"
    slug = re.sub(r"[^a-z0-9]+", "-", label.strip().lower()).strip("-")
    return slug or "candidate"
