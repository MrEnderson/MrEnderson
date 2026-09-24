"""Static, non-destructive check of the v0.2.5 DELEGATION + AUTHORITY
ATTENUATION *design* artifacts
(docs/V0_2_5_DELEGATION_AND_AUTHORITY_SECURITY_DESIGN.md /
docs/v0.2.5_delegation_authority_design.json).

DESIGN CONTRACT CHECK -- v0.2.5 is DESIGN_ONLY. There is no production
delegation code to exercise, and this checker deliberately imports none.
It verifies, WITHOUT touching the database, `.env`, the network,
credentials, providers or any ToolAdapter:

  - both design artifacts exist, the JSON is valid, and their committed
    content is identical to the approved design commit 1e242b8;
  - status == DESIGN_ONLY, implementation_authorized is false,
    production_code_created is false, and no artifact uses a
    COMPLETE / IMPLEMENTED / PRODUCTION_READY status. These are HISTORICAL
    assertions about the design checkpoint, not the current repository
    state (F-04): the later, separately authorized v0.2.5.1 phase is recorded
    in docs/V0_2_5_1_AUTHORITY_CONTRACTS_AND_ALGEBRA.md, whose phase-status
    lines (v0.2.5.1 only; v0.2.5.2+ and v0.2.6 NOT AUTHORIZED) are checked;
  - every required invariant (DI-*), proof obligation (PO-*), threat
    (T-*), revocation threat (R-*), denial-laundering row (D-*) and change
    request (CR-*) is present in the JSON, and each ID also appears in the
    Markdown design;
  - every threat row carries all seven required columns;
  - the hostile review (HR-1) lists findings HR-01..HR-28 and design approval
    questions DA-01..DA-10; every CRITICAL/HIGH/MEDIUM/LOW finding is
    REMEDIATED;
  - Human Owner design approval is recorded separately from implementation
    authorization: human_design_approval == APPROVED and design_approved is
    true, while implementation / pipeline integration / migration /
    frozen-code / P5-protocol / v0.2.6 authorization flags are all exactly
    false; each DA carries exactly the Human Owner's decision (DA-03 is
    APPROVED_WITH_REWORDING with the exact approved rule text);
  - the DA-03 P5 boundary holds (proposal != authority, STOP at the
    authorization boundary, OQ-10 OPEN), hostile checks DA03-A..G all
    FAIL_CLOSED, and "owner adoption" appears only as a REJECTED
    interpretation;
  - constitutional blockers CC-01 and CC-02 are present and not waived, the
    accepted limitations and reconfirmed attenuation invariants are present;
  - the section 26 reason codes agree between the Markdown and JSON; threat,
    revocation, denial-laundering and DA-03 hostile rows name no reason-like
    identifier outside that table (plus evaluation outcomes and computed
    lifecycle states); T-10 names CEILING_EXCEEDED, the table's code for a
    P-tier above the effective ceiling;
  - every constitutional classification uses one of the allowed labels;
  - the AuthorityScope dimensions in the JSON equal those in the Markdown
    section 3.2 table (MD/JSON drift check);
  - the Markdown answers all 22 design review questions and carries the
    human-review checkpoint line;
  - forbidden implementation paths (`app/delegation`, `app/authority`) are
    absent; the v0.2.5.1 pure contracts (PTier, PrincipalKind, PrincipalRef,
    ObjectiveRef, AuthorityScope) are defined ONLY in `app/authority_contracts/`,
    and no module anywhere under `app/` defines a later-stage delegation or
    authority class (records, roots, stores, evaluation, engines);
  - no file under `app/` outside `app/authority_contracts/`, under
    `migrations/` or `alembic.ini` is new or modified, and the ONLY new or
    modified files anywhere in the repository are the exact v0.2.5.1 file
    set (whole-repo `git status` allowlist, which catches production code
    placed under any other name or path; the committed v0.2.5 design
    artifacts are no longer in it);
  - the Alembic revision graph (parsed from files, no DB) has the single
    head `7f2c9a1e4b6d`;
  - the v0.1.3 tag still peels to the frozen commit;
  - the ToolAdapter inventory is still exactly `['file.create_sandboxed']`.

This checker is supplemental evidence, not a proof: it verifies presence,
structure and cross-references, not the correctness of the design argument
(see the design's Part II section Q for its blind spots).

This is a read-only validator. It does not modify files, the database or
Git; it does not call external APIs, access the network, execute providers
or invoke ToolAdapters; it requires no secrets.

Usage:
    python scripts/check_v025_design_contract.py

Exit code 0 = design artifacts match expectations. Exit code 1 = a
discrepancy was found (printed).
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent

_MD_PATH = Path("docs") / "V0_2_5_DELEGATION_AND_AUTHORITY_SECURITY_DESIGN.md"
_JSON_PATH = Path("docs") / "v0.2.5_delegation_authority_design.json"

_EXPECTED_PREDECESSOR_COMMIT = "d10fbbbf4b697eba822a89495ae0ebd276b3101d"
_EXPECTED_B11_COMMIT = "21dc3d022165162550ca24c518a0fb11f445238d"
_EXPECTED_V013_COMMIT = "be667b177f27839f5a370939bca045b7fb06eb4c"
_EXPECTED_ALEMBIC_HEAD = "7f2c9a1e4b6d"
_EXPECTED_TOOL_ADAPTERS = ["file.create_sandboxed"]

# F-04: the approved design artifacts are immutable; their committed content
# must equal this commit's blobs.
_APPROVED_DESIGN_COMMIT = "1e242b827f46de42064ea0965f59e8c2bf82591c"
# The single phase the Human Owner has authorized since the design checkpoint.
_AUTHORIZED_PHASE = "v0.2.5.1"
_V0251_DOC_PATH = Path("docs") / "V0_2_5_1_AUTHORITY_CONTRACTS_AND_ALGEBRA.md"
_V0251_PHASE_RECORD = (
    re.compile(r"^authorized_phase += v0\.2\.5\.1 only \(pure contracts \+ algebra\)$", re.MULTILINE),
    re.compile(r"^v0\.2\.5\.2\+ += NOT AUTHORIZED$", re.MULTILINE),
    re.compile(r"^v0\.2\.6 += NOT AUTHORIZED$", re.MULTILINE),
    re.compile(r"immutable\s+historical\s+design-approval\s+evidence"),
)

_FORBIDDEN_PATHS = [Path("app") / "delegation", Path("app") / "authority"]
_FORBIDDEN_STATUS_WORDS = ("COMPLETE", "IMPLEMENTED", "PRODUCTION_READY")
# v0.2.5.1 (Human-Owner-authorized pure contracts + algebra): these contract
# names may exist, but only inside this package.
_V0251_PACKAGE = "app/authority_contracts"
_V0251_CONTRACT_CLASS_NAMES = {"PrincipalRef", "PrincipalKind", "PTier", "ObjectiveRef", "AuthorityScope"}
# Later-stage contract names proposed by the design; none may exist as a class
# anywhere in app/ (v0.2.5.2+ requires separate authorization).
_DESIGN_ONLY_CLASS_NAMES = {
    "RedelegationPolicy", "RootAuthorization", "DelegationRequest", "DelegationRecord",
    "DelegationParentRef", "RevocationRecord", "AuthorityEvaluation", "SystemPolicyCeiling",
    "DelegationStore", "DelegationEngine", "AuthorityEngine",
}

_CHECKPOINT_LINE = "NO v0.2.5 PRODUCTION IMPLEMENTATION HAS BEEN AUTHORIZED OR CREATED."
_THREAT_COLUMNS = (
    "id", "attack", "precondition", "expected_fail_closed_behavior",
    "required_invariant", "future_enforcement_owner", "test_strategy",
)


def _ids(prefix: str, count: int) -> list[str]:
    return [f"{prefix}-{i:02d}" for i in range(1, count + 1)]


_ALLOWED_CHANGED_FILES = {
    "app/authority_contracts/__init__.py",
    "app/authority_contracts/contracts.py",
    "app/authority_contracts/algebra.py",
    "docs/V0_2_5_1_AUTHORITY_CONTRACTS_AND_ALGEBRA.md",
    "tests/test_v0251_hostile_authority_algebra.py",
    "scripts/check_v025_design_contract.py",
    "tests/test_v025_design_contract.py",
}
_ALLOWED_CLASSIFICATIONS = (
    "compatible interpretation",
    "strengthening",
    "explicit refinement requiring authorization",
)
_EXPECTED_DIMENSIONS = {
    "schema_version", "vocabulary_version", "permission_ceiling",
    "action_types", "objective_ref", "expires_at",
}
_HR_IDS = _ids("HR", 28)
_DA_IDS = _ids("DA", 10)

# Human Owner design decisions. Design approval only -- never implementation.
_EXPECTED_DA_DECISIONS = {i: "APPROVED" for i in _DA_IDS}
_EXPECTED_DA_DECISIONS["DA-03"] = "APPROVED_WITH_REWORDING"
_DA03_APPROVED_RULE = (
    "AI agents may never hold standing delegated P5 authority under v0.2.5. "
    "An AI agent may formulate or propose a P5 action, but v0.2.5 grants no "
    "authority to execute that action. Any future P5 execution path requires a "
    "separately designed, hostile-reviewed and Human-Owner-approved P5 "
    "authorization protocol."
)
# HISTORICAL design-checkpoint assertions (F-04). These flags record the
# authorization state AT the v0.2.5 design checkpoint (_APPROVED_DESIGN_COMMIT)
# and stay false forever as immutable design-approval evidence. They do not
# describe later, separately Human-Owner-authorized phases: current phase
# allowances live in check_repository() / check_phase_record() and cover
# v0.2.5.1 only.
_MUST_BE_FALSE = (
    "implementation_authorized", "production_code_created",
    "pipeline_integration_authorized", "migration_authorized",
    "frozen_code_changes_authorized", "p5_execution_protocol_authorized",
    "v0_2_6_authorized",
)
_P5_BOUNDARY_FALSE = (
    "agent_p5_proposal_grants_authority", "human_approval_grants_standing_p5",
    "approval_transferable_between_actions", "approval_mutates_delegation_ceiling",
    "p5_issuable_to_agent", "p5_execution_protocol_exists",
)
_DA03_CHECK_IDS = [f"DA03-{c}" for c in "ABCDEFG"]
_CC_IDS = ["CC-01", "CC-02"]
_CC02_NON_CLAIMS = {
    "delegation lineage != semantic intent equivalence",
    "delegation lineage != split/recombine detection",
}
_REQUIRED_ALGEBRA = (
    "child.scope <= parent.redelegable_scope",
    "child.redelegable_scope <= child.scope",
    "Authority(leaf) <= ... <= Authority(root) <= Human Owner authorization",
)
_REQUIRED_LIMITATIONS = ("OQ-10 remains OPEN", "no P5 execution protocol exists in v0.2.5")
# "Owner adoption" was rejected as a P5 mechanism (DA-03); it may appear only
# where the text itself marks it REJECTED (or in a FAIL_CLOSED hostile row).
_ADOPTION_RE = re.compile(r"owner[- ]adopt|adopts? (it|the proposal|an agent's draft|a draft)", re.IGNORECASE)
# Reason-code vocabulary. Threat-style rows may name only a section 26 reason
# code, an AuthorityEvaluation outcome, a computed lifecycle state, or one of
# these non-reason labels -- never an ad-hoc alias of a reason code.
_EVALUATION_OUTCOMES = {"WITHIN_SCOPE", "OUTSIDE_SCOPE", "LINEAGE_INVALID"}
_NON_REASON_LABELS = {"FAIL_CLOSED", "HUMAN_OWNER", "EXTERNAL_ACTION"}
_CAPS_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
_VOCAB_ROW_KEYS = ("threat_matrix", "revocation_threat_matrix", "denial_laundering_matrix", "da03_hostile_checks")
_MD_VOCAB_ROW_RE = re.compile(r"^\| (?:T|R|D|DA03)-[0-9A-Z]+ \|.*$", re.MULTILINE)
# T-10 (P3 -> P5) fails on the tier ceiling: its expected reason is pinned to
# the table code whose meaning is "Required P-tier above effective ceiling".
_T10_REASON_CODE = "CEILING_EXCEEDED"
_MD_STATUS_LINES = (
    "status = DESIGN_ONLY", "human_design_approval = APPROVED", "design_approved = true",
    *(f"{flag} = false" for flag in _MUST_BE_FALSE if flag != "production_code_created"),
)

_REQUIRED_IDS: dict[str, list[str]] = {
    "invariants": _ids("DI", 19),
    "proof_obligations": _ids("PO", 19),
    "threat_matrix": _ids("T", 57),
    "revocation_threat_matrix": _ids("R", 10),
    "denial_laundering_matrix": _ids("D", 8),
    "change_requests_requiring_separate_authorization": _ids("CR", 5),
}


def check_design_artifacts(data: Any, md_text: str) -> list[str]:
    """Pure check of the two design artifacts. Returns a list of problems."""
    problems: list[str] = []
    if not isinstance(data, dict):
        return ["design JSON top level is not an object"]

    if data.get("version") != "v0.2.5":
        problems.append(f"version is {data.get('version')!r}, expected 'v0.2.5'")
    if data.get("status") != "DESIGN_ONLY":
        problems.append(f"status is {data.get('status')!r}, expected 'DESIGN_ONLY'")
    for flag in _MUST_BE_FALSE:
        if data.get(flag) is not False:
            problems.append(f"{flag} must be exactly false")
    if data.get("human_design_approval") != "APPROVED":
        problems.append("human_design_approval must be 'APPROVED'")
    if data.get("design_approved") is not True:
        problems.append("design_approved must be exactly true")
    if data.get("predecessor_commit") != _EXPECTED_PREDECESSOR_COMMIT:
        problems.append(f"predecessor_commit is {data.get('predecessor_commit')!r}")
    if data.get("b11_commit") != _EXPECTED_B11_COMMIT:
        problems.append(f"b11_commit is {data.get('b11_commit')!r}")
    if data.get("alembic_head_expected") != _EXPECTED_ALEMBIC_HEAD:
        problems.append("alembic_head_expected does not match the frozen head")
    if data.get("tool_adapters_expected") != _EXPECTED_TOOL_ADAPTERS:
        problems.append("tool_adapters_expected does not match the frozen inventory")
    if data.get("design_review_questions_answered") != 22:
        problems.append("design_review_questions_answered must be 22")

    for key, expected in _REQUIRED_IDS.items():
        rows = data.get(key)
        if not isinstance(rows, list):
            problems.append(f"JSON key {key!r} missing or not a list")
            continue
        found = [r.get("id") for r in rows if isinstance(r, dict)]
        missing = [i for i in expected if i not in found]
        if missing:
            problems.append(f"{key}: missing IDs {missing}")
        if len(found) != len(set(found)):
            problems.append(f"{key}: duplicate IDs")
        for i in expected:
            if not re.search(rf"\b{re.escape(i)}\b", md_text):
                problems.append(f"{i} is in the JSON but not referenced in the Markdown design")

    for row in data.get("threat_matrix") or []:
        if isinstance(row, dict):
            absent = [c for c in _THREAT_COLUMNS if not str(row.get(c, "")).strip()]
            if absent:
                problems.append(f"threat {row.get('id')!r} lacks columns {absent}")

    problems.extend(_check_hostile_review(data, md_text))
    problems.extend(_check_human_decisions(data, md_text))
    problems.extend(_check_reason_vocabulary(data, md_text))

    # Status discipline in both artifacts.
    for line in _MD_STATUS_LINES:
        if not re.search(rf"^{re.escape(line)}$", md_text, flags=re.MULTILINE):
            problems.append(f"Markdown must state {line!r}")
    for word in _FORBIDDEN_STATUS_WORDS:
        if re.search(rf"status\s*[=:]\s*\"?{word}\b", md_text):
            problems.append(f"Markdown declares a forbidden status {word!r}")
        if isinstance(data.get("status"), str) and word in data["status"]:
            problems.append(f"JSON status uses forbidden word {word!r}")
    if _CHECKPOINT_LINE not in md_text:
        problems.append("Markdown lacks the human-review checkpoint line")
    for q in range(1, 23):
        if not re.search(rf"^### Q{q}\. ", md_text, flags=re.MULTILINE):
            problems.append(f"Markdown does not answer design review question Q{q}")
    return problems


def _check_hostile_review(data: dict, md_text: str) -> list[str]:
    """HR-1 review block, DA questions, classification labels, and the
    AuthorityScope dimension set in both artifacts."""
    problems: list[str] = []
    review = data.get("hostile_review")
    if not isinstance(review, dict) or review.get("status") != "DESIGN_ONLY":
        problems.append("hostile_review block missing or not DESIGN_ONLY")
        review = {}
    findings = [f for f in review.get("findings") or [] if isinstance(f, dict)]
    if [f.get("id") for f in findings] != _HR_IDS:
        problems.append(f"hostile_review findings must be exactly {_HR_IDS[0]}..{_HR_IDS[-1]} in order")
    for f in findings:
        sev = f.get("severity")
        if sev not in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
            problems.append(f"{f.get('id')}: invalid severity {sev!r}")
        elif sev != "INFO" and f.get("status") != "REMEDIATED":
            problems.append(f"{f.get('id')}: {sev} finding is not REMEDIATED")
        if not re.search(rf"\b{re.escape(str(f.get('id')))}\b", md_text):
            problems.append(f"{f.get('id')} is not referenced in the Markdown design")
    if review.get("critical_findings") != 0:
        problems.append("hostile_review.critical_findings must be 0")

    questions = [q for q in data.get("design_approval_questions") or [] if isinstance(q, dict)]
    if [q.get("id") for q in questions] != _DA_IDS:
        problems.append("design_approval_questions must be exactly DA-01..DA-10")
    for q in questions:
        if f"**{q.get('id')} " not in md_text:
            problems.append(f"{q.get('id')} is not asked in the Markdown design")

    classification = data.get("constitutional_classification")
    if not classification:
        problems.append("constitutional_classification missing")
    for row in classification or []:
        label = str(row.get("classification", ""))
        if label not in _ALLOWED_CLASSIFICATIONS and not label.startswith("conflict"):
            problems.append(f"classification {label!r} for {row.get('rule')!r} is not an allowed label")

    dims = data.get("authority_scope_dimensions_v025")
    if not isinstance(dims, dict) or set(dims) != _EXPECTED_DIMENSIONS:
        problems.append(f"JSON AuthorityScope dimensions {sorted(dims or [])} != {sorted(_EXPECTED_DIMENSIONS)}")
    section = md_text.split("### 3.2 AuthorityScope", 1)[-1].split("\n### ", 1)[0]
    md_dims = set(re.findall(r"^\| `([a-z_]+)` \|", section, flags=re.MULTILINE))
    if md_dims != _EXPECTED_DIMENSIONS:
        problems.append(f"Markdown section 3.2 dimensions {sorted(md_dims)} != {sorted(_EXPECTED_DIMENSIONS)}")
    return problems


def _check_reason_vocabulary(data: dict, md_text: str) -> list[str]:
    """Section 26 reason codes are the only reason vocabulary: the MD and JSON
    tables agree, threat-style rows use no undefined reason-like identifier,
    and T-10 names the table's ceiling code."""
    problems: list[str] = []
    codes = {r.get("code") for r in data.get("reason_codes") or [] if isinstance(r, dict)}
    section = md_text.split("## 26. Reason codes", 1)[-1].split("\n## ", 1)[0]
    md_codes = set(re.findall(r"^\| `([A-Z0-9_]+)` \|", section, flags=re.MULTILINE))
    if not codes or md_codes != codes:
        problems.append(f"reason codes differ between Markdown section 26 and JSON: {sorted(md_codes ^ codes)}")
    meanings = {r.get("code"): str(r.get("meaning", "")) for r in data.get("reason_codes") or [] if isinstance(r, dict)}
    if "ceiling" not in meanings.get(_T10_REASON_CODE, ""):
        problems.append(f"{_T10_REASON_CODE} must be the reason code for exceeding the P-tier ceiling")

    lifecycle = data.get("lifecycle") if isinstance(data.get("lifecycle"), dict) else {}
    allowed = codes | _EVALUATION_OUTCOMES | _NON_REASON_LABELS | set(lifecycle.get("computed_states") or [])
    texts = [
        (f"JSON {row.get('id')}", str(value))
        for key in _VOCAB_ROW_KEYS for row in data.get(key) or [] if isinstance(row, dict)
        for value in row.values()
    ]
    texts += [(f"Markdown {m.group(0).split('|')[1].strip()}", m.group(0)) for m in _MD_VOCAB_ROW_RE.finditer(md_text)]
    for where, text in texts:
        for token in sorted(set(_CAPS_TOKEN_RE.findall(text)) - allowed):
            problems.append(f"{where} uses {token!r}, which is not a section 26 reason code or defined outcome")

    t10 = next((r for r in data.get("threat_matrix") or [] if isinstance(r, dict) and r.get("id") == "T-10"), {})
    for column in ("expected_fail_closed_behavior", "test_strategy"):
        if _T10_REASON_CODE not in str(t10.get(column, "")):
            problems.append(f"T-10 {column} must name the reason code {_T10_REASON_CODE}")
    md_t10 = re.search(r"^\| T-10 \|.*$", md_text, flags=re.MULTILINE)
    if not md_t10 or md_t10.group(0).count(_T10_REASON_CODE) < 2:
        problems.append(f"Markdown T-10 row must name the reason code {_T10_REASON_CODE}")
    return problems


def _json_strings(node: Any):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _json_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _json_strings(value)


def _check_human_decisions(data: dict, md_text: str) -> list[str]:
    """Human Owner DA decisions, the DA-03 P5 boundary, constitutional
    blockers, accepted limitations and the reconfirmed attenuation algebra."""
    problems: list[str] = []
    questions = {q.get("id"): q for q in data.get("design_approval_questions") or [] if isinstance(q, dict)}
    for da_id, decision in _EXPECTED_DA_DECISIONS.items():
        q = questions.get(da_id, {})
        if q.get("decision") != decision or q.get("approved") is not True:
            problems.append(f"{da_id} must record the Human Owner decision {decision!r} with approved=true")
        if q.get("decided_by") != "HUMAN_OWNER":
            problems.append(f"{da_id} decided_by must be HUMAN_OWNER")
        if q.get("implementation_authorized") is not False:
            problems.append(f"{da_id} must keep implementation_authorized exactly false")
        if not re.search(rf"^\| {re.escape(da_id)} \| {re.escape(decision)} \|", md_text, flags=re.MULTILINE):
            problems.append(f"Markdown Part III does not record {da_id} as {decision}")
    if questions.get("DA-03", {}).get("approved_rule") != _DA03_APPROVED_RULE:
        problems.append("DA-03 approved_rule is not the exact Human Owner wording")
    if md_text.count(_DA03_APPROVED_RULE) < 2:
        problems.append("Markdown must state the exact DA-03 approved rule (section 3.7 and Part III)")

    p5 = data.get("p5_boundary")
    if not isinstance(p5, dict):
        problems.append("p5_boundary block missing")
        p5 = {}
    if p5.get("approved_rule") != _DA03_APPROVED_RULE:
        problems.append("p5_boundary.approved_rule is not the exact DA-03 wording")
    for flag in _P5_BOUNDARY_FALSE:
        if p5.get(flag) is not False:
            problems.append(f"p5_boundary.{flag} must be exactly false")
    if p5.get("p5_proposal_outcome") != "STOP_AT_AUTHORIZATION_BOUNDARY":
        problems.append("p5_boundary.p5_proposal_outcome must be STOP_AT_AUTHORIZATION_BOUNDARY")
    if p5.get("oq_10_status") != "OPEN":
        problems.append("OQ-10 must remain OPEN")
    if "P5 proposal         \u2192  STOP at authorization boundary" not in md_text:
        problems.append("Markdown lacks 'P5 proposal -> STOP at authorization boundary'")

    checks = [c for c in data.get("da03_hostile_checks") or [] if isinstance(c, dict)]
    if [c.get("id") for c in checks] != _DA03_CHECK_IDS:
        problems.append("da03_hostile_checks must be exactly DA03-A..DA03-G in order")
    for c in checks:
        if c.get("expected_result") != "FAIL_CLOSED" or not str(c.get("reason", "")).strip():
            problems.append(f"{c.get('id')} must FAIL_CLOSED with a reason")
        if not re.search(rf"^\| {re.escape(str(c.get('id')))} \|.*\| FAIL_CLOSED \|", md_text, flags=re.MULTILINE):
            problems.append(f"{c.get('id')} is not a FAIL_CLOSED row in the Markdown design")

    for line in md_text.splitlines():
        if _ADOPTION_RE.search(line) and "REJECTED" not in line and "FAIL_CLOSED" not in line:
            problems.append(f"Markdown uses owner adoption as a mechanism: {line.strip()[:100]!r}")
    # Hostile-check rows describe rejected attacks and are verified FAIL_CLOSED above.
    for s in _json_strings({k: v for k, v in data.items() if k != "da03_hostile_checks"}):
        if _ADOPTION_RE.search(s) and "REJECTED" not in s and "FAIL_CLOSED" not in s:
            problems.append(f"JSON uses owner adoption as a mechanism: {s[:100]!r}")

    blockers = {b.get("id"): b for b in data.get("constitutional_blockers") or [] if isinstance(b, dict)}
    for cc in _CC_IDS:
        b = blockers.get(cc, {})
        if b.get("waived") is not False or b.get("status") != "BLOCKING":
            problems.append(f"{cc} must be present, BLOCKING and not waived")
        if not re.search(rf"\*\*{cc} \u2014 ", md_text):
            problems.append(f"{cc} is not stated in the Markdown design")
    if not _CC02_NON_CLAIMS <= set(blockers.get("CC-02", {}).get("non_claims") or []):
        problems.append("CC-02 must disclaim semantic intent equivalence and split/recombine detection")

    limitations = data.get("accepted_design_limitations") or []
    for item in _REQUIRED_LIMITATIONS:
        if item not in limitations:
            problems.append(f"accepted_design_limitations lacks {item!r}")
    algebra = data.get("authority_algebra_reconfirmed") or []
    for formula in _REQUIRED_ALGEBRA:
        if formula not in algebra:
            problems.append(f"authority_algebra_reconfirmed lacks {formula!r}")
    for formula in ("child.scope              \u2264  parent.redelegable_scope",
                    "child.redelegable_scope  \u2264  child.scope"):
        if formula not in md_text:
            problems.append(f"Markdown Part III lacks attenuation formula {formula!r}")
    return problems


def _alembic_heads(versions_dir: Path) -> list[str]:
    """Heads of the revision graph, parsed from migration files (no DB)."""
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in versions_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        values: dict[str, Any] = {}
        for node in tree.body:
            targets = []
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets, value = [node.target], node.value
            for t in targets:
                if isinstance(t, ast.Name) and t.id in ("revision", "down_revision"):
                    values[t.id] = ast.literal_eval(value)
        if "revision" not in values:
            continue
        revisions.add(values["revision"])
        down = values.get("down_revision")
        if isinstance(down, str):
            parents.add(down)
        elif isinstance(down, (tuple, list)):
            parents.update(down)
    return sorted(revisions - parents)


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=_REPO_ROOT, capture_output=True, text=True, check=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    # rstrip only: a leading space is the first porcelain status column (F-02).
    return out.stdout.rstrip()


def _check_contract_class_placement(repo_root: Path) -> list[str]:
    """v0.2.5.1 contracts only inside the package; later-stage contracts nowhere."""
    problems: list[str] = []
    for path in (repo_root / "app").rglob("*.py"):
        rel = path.relative_to(repo_root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            problems.append(f"could not parse {rel}: {exc}")
            continue
        in_package = rel.startswith(_V0251_PACKAGE + "/")
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if node.name in _DESIGN_ONLY_CLASS_NAMES:
                problems.append(f"design-only contract {node.name!r} is defined in production code: {rel}")
            elif node.name in _V0251_CONTRACT_CLASS_NAMES and not in_package:
                problems.append(f"v0.2.5.1 contract {node.name!r} is defined outside {_V0251_PACKAGE}: {rel}")
    return problems


def check_phase_record(md_text: str) -> list[str]:
    """F-04: the v0.2.5.1 document must record that the historical design
    flags are checkpoint evidence and that only v0.2.5.1 is authorized."""
    return [
        f"{_V0251_DOC_PATH.as_posix()} does not record the phase status {pattern.pattern!r}"
        for pattern in _V0251_PHASE_RECORD
        if not pattern.search(md_text)
    ]


def check_repository(repo_root: Path) -> list[str]:
    problems: list[str] = []

    changed_design = _git("diff", "--name-only", _APPROVED_DESIGN_COMMIT, "--",
                          _MD_PATH.as_posix(), _JSON_PATH.as_posix())
    if changed_design is None:
        problems.append(f"git unavailable: cannot compare the design artifacts with {_APPROVED_DESIGN_COMMIT}")
    elif changed_design:
        problems.append(f"approved design artifacts differ from {_APPROVED_DESIGN_COMMIT}: {changed_design!r}")

    doc = repo_root / _V0251_DOC_PATH
    if not doc.exists():
        problems.append(f"missing phase record: {_V0251_DOC_PATH.as_posix()}")
    else:
        problems.extend(check_phase_record(doc.read_text(encoding="utf-8")))

    for rel in _FORBIDDEN_PATHS:
        if (repo_root / rel).exists():
            problems.append(f"forbidden implementation path exists: {rel.as_posix()}")

    problems.extend(_check_contract_class_placement(repo_root))

    heads = _alembic_heads(repo_root / "migrations" / "versions")
    if heads != [_EXPECTED_ALEMBIC_HEAD]:
        problems.append(f"Alembic heads are {heads!r}, expected [{_EXPECTED_ALEMBIC_HEAD!r}]")

    modified = _git("status", "--porcelain", "--", "app", "migrations", "alembic.ini")
    if modified is None:
        problems.append("git unavailable: cannot verify app/ and migrations/ are unmodified")
    else:
        outside = [
            line for line in modified.splitlines()
            if not line[3:].strip().strip('"').startswith(_V0251_PACKAGE + "/")
        ]
        if outside:
            problems.append(
                "app/ or migrations/ has changes outside the v0.2.5.1 package:\n" + "\n".join(outside)
            )

    everything = _git("status", "--porcelain", "-uall")
    if everything is None:
        problems.append("git unavailable: cannot verify the changed-file allowlist")
    else:
        for line in everything.splitlines():
            path = line[3:].strip().strip('"')
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            if path not in _ALLOWED_CHANGED_FILES:
                problems.append(f"file outside the v0.2.5.1 allowlist is new/modified: {line.strip()}")

    v013 = _git("rev-parse", "v0.1.3^{}")
    if v013 != _EXPECTED_V013_COMMIT:
        problems.append(f"v0.1.3^{{}} resolves to {v013!r}, expected {_EXPECTED_V013_COMMIT}")

    try:
        sys.path.insert(0, str(repo_root))
        from app.decision_intelligence.tool_adapters import build_default_adapter_registry

        adapters = sorted(build_default_adapter_registry().list_tool_names())
        if adapters != _EXPECTED_TOOL_ADAPTERS:
            problems.append(f"ToolAdapter inventory is {adapters!r}, expected {_EXPECTED_TOOL_ADAPTERS!r}")
    except ImportError as exc:
        problems.append(f"Could not import ToolAdapterRegistry to verify inventory: {exc}")
    return problems


def main() -> int:
    problems: list[str] = []
    md_file = _REPO_ROOT / _MD_PATH
    json_file = _REPO_ROOT / _JSON_PATH
    data: Any = None
    md_text = ""
    for f in (md_file, json_file):
        if not f.exists():
            problems.append(f"missing design artifact: {f.relative_to(_REPO_ROOT).as_posix()}")
    if not problems:
        md_text = md_file.read_text(encoding="utf-8")
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            problems.append(f"design JSON is invalid: {exc}")
    if data is not None:
        problems.extend(check_design_artifacts(data, md_text))
    problems.extend(check_repository(_REPO_ROOT))

    if problems:
        print("v0.2.5 DESIGN CONTRACT CHECK: DISCREPANCY FOUND")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("v0.2.5 DESIGN CONTRACT CHECK: OK")
    print("  Human Owner design approval: DA-01..DA-10 recorded (DA-03 APPROVED_WITH_REWORDING)")
    print(f"  Historical design checkpoint ({_APPROVED_DESIGN_COMMIT[:7]}, artifacts unchanged): "
          "status=DESIGN_ONLY, implementation_authorized=false")
    print(f"  Current authorized phase: {_AUTHORIZED_PHASE} only (pure contracts + algebra); "
          "v0.2.5.2+ and v0.2.6 NOT authorized")
    print(f"  Predecessor: {data.get('predecessor_version')} ({data.get('predecessor_commit')})")
    for key, expected in _REQUIRED_IDS.items():
        print(f"  {key}: {len(expected)} required IDs present")
    print(f"  Alembic head: {_EXPECTED_ALEMBIC_HEAD}")
    print(f"  ToolAdapters: {_EXPECTED_TOOL_ADAPTERS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
