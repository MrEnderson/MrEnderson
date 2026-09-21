"""Research Intelligence pipeline (v0.1.2).

Jarvis must know WHAT evidence it needs before searching, know what each
source can prove, reject irrelevant evidence, track coverage per candidate,
and refuse to rank candidates that have not been researched to a comparable
minimum standard.

Pipeline (see docs/research_intelligence.md):

    Objective -> Requirement Planning -> Candidate Discovery ->
    Source-Aware Search -> Relevance Filter -> Evidence Classification ->
    Coverage Matrix -> Gap Search -> Completeness Gate -> Strategy -> QA

Every module here is deterministic, code-level logic — no model calls. It
complements (never replaces) the existing model-driven Research/Strategy/QA
agents, the same defense-in-depth pattern as app/security/evidence_qa.py.
"""
