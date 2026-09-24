"""DESIGN CONTRACT TEST -- v0.2.5 Delegation + Authority Attenuation.

v0.2.5 is DESIGN_ONLY: no production delegation code exists. These tests
exercise ONLY the design artifacts and scripts/check_v025_design_contract.py.
They say nothing about runtime delegation behavior.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_v025_design_contract", _REPO_ROOT / "scripts" / "check_v025_design_contract.py"
)
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)


@pytest.fixture(scope="module")
def artifacts():
    data = json.loads((_REPO_ROOT / checker._JSON_PATH).read_text(encoding="utf-8"))
    md = (_REPO_ROOT / checker._MD_PATH).read_text(encoding="utf-8")
    return data, md


def test_design_checker_passes_on_repository():
    assert checker.main() == 0


def test_design_artifacts_are_consistent(artifacts):
    data, md = artifacts
    assert checker.check_design_artifacts(data, md) == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(status="IMPLEMENTED"),
        lambda d: d.update(status="COMPLETE"),
        lambda d: d.update(implementation_authorized=True),
        lambda d: d.update(implementation_authorized="false"),
        lambda d: d.pop("implementation_authorized"),
        lambda d: d.update(production_code_created=True),
        lambda d: d["threat_matrix"].pop(),
        lambda d: d["threat_matrix"].append(copy.deepcopy(d["threat_matrix"][0])),
        lambda d: d["threat_matrix"][0].update(test_strategy=""),
        lambda d: d["proof_obligations"].pop(0),
        lambda d: d["revocation_threat_matrix"].pop(),
        lambda d: d["denial_laundering_matrix"].pop(),
        lambda d: d.update(tool_adapters_expected=["file.create_sandboxed", "shell.run"]),
        # HR-1 hostile review gating
        lambda d: d["hostile_review"]["findings"][0].update(status="OPEN"),  # HR-01 HIGH left open
        lambda d: d["hostile_review"]["findings"][5].update(severity="SEVERE"),
        lambda d: d["hostile_review"]["findings"].pop(),
        lambda d: d["hostile_review"].update(critical_findings=1),
        lambda d: d["design_approval_questions"].pop(),
        # Human Owner design approval != implementation authorization
        lambda d: d.update(status="DESIGN_APPROVED"),
        lambda d: d.update(design_approved=False),
        lambda d: d.update(human_design_approval="PENDING"),
        lambda d: d.update(pipeline_integration_authorized=True),
        lambda d: d.update(migration_authorized=True),
        lambda d: d.update(frozen_code_changes_authorized=True),
        lambda d: d.update(p5_execution_protocol_authorized=True),
        lambda d: d.pop("v0_2_6_authorized"),
        lambda d: d["design_approval_questions"][2].update(decision="APPROVED"),  # DA-03 rewording dropped
        lambda d: d["design_approval_questions"][4].update(decision=None, approved=None),
        lambda d: d["design_approval_questions"][0].update(decided_by="AGENT"),
        lambda d: d["design_approval_questions"][9].update(implementation_authorized=True),
        lambda d: d["design_approval_questions"][2].update(approved_rule="Owner adoption allows P5."),
        # DA-03 P5 boundary and hostile checks A..G
        lambda d: d["p5_boundary"].update(human_approval_grants_standing_p5=True),
        lambda d: d["p5_boundary"].update(agent_p5_proposal_grants_authority=True),
        lambda d: d["p5_boundary"].update(approval_mutates_delegation_ceiling=True),
        lambda d: d["p5_boundary"].update(p5_execution_protocol_exists=True),
        lambda d: d["p5_boundary"].update(p5_proposal_outcome="ALLOW_WITH_APPROVAL"),
        lambda d: d["p5_boundary"].update(oq_10_status="CLOSED"),
        lambda d: d["da03_hostile_checks"].pop(),
        lambda d: d["da03_hostile_checks"][4].update(expected_result="ALLOW"),
        lambda d: d.update(p5_policy="agent P5 proposals reachable via owner adoption"),
        # Constitutional blockers, limitations, algebra
        lambda d: d["constitutional_blockers"][0].update(waived=True),
        lambda d: d["constitutional_blockers"].pop(),
        lambda d: d["constitutional_blockers"][1].update(non_claims=[]),
        lambda d: d["accepted_design_limitations"].remove("OQ-10 remains OPEN"),
        lambda d: d["authority_algebra_reconfirmed"].remove("child.redelegable_scope <= child.scope"),
        lambda d: d["constitutional_classification"][0].update(classification="looks fine"),
        lambda d: d["authority_scope_dimensions_v025"].pop("objective_ref"),
        lambda d: d["authority_scope_dimensions_v025"].update(tenant_scope="ALL"),
    ],
)
def test_design_checker_rejects_tampered_json(artifacts, mutate):
    data, md = artifacts
    tampered = copy.deepcopy(data)
    mutate(tampered)
    assert checker.check_design_artifacts(tampered, md)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m.replace(checker._CHECKPOINT_LINE, ""),
        lambda m: m.replace("status = DESIGN_ONLY", "status = PRODUCTION_READY"),
        lambda m: m.replace("### Q17. ", "### Q17 "),
        lambda m: m.replace("T-44", "T-XX"),
        lambda m: m.replace("| `vocabulary_version` |", "| `vocab` |"),  # MD/JSON dimension drift
        lambda m: m.replace("**DA-06 ", "**DA-6 "),
        lambda m: m.replace("implementation_authorized = false", "implementation_authorized = true"),
        lambda m: m.replace("p5_execution_protocol_authorized = false", ""),
        lambda m: m.replace("| DA-03 | APPROVED_WITH_REWORDING |", "| DA-03 | APPROVED |"),
        lambda m: m.replace(checker._DA03_APPROVED_RULE, "Owner adoption grants P5."),
        lambda m: m.replace("| FAIL_CLOSED | Approval writes nothing", "| ALLOW | Approval writes nothing"),
        lambda m: m + "\nThe owner adopts the proposal as an owner-requested action.\n",
        lambda m: m.replace("**CC-02 \u2014 ", "**CC 02 \u2014 "),
        lambda m: m.replace("child.redelegable_scope  \u2264  child.scope", ""),
    ],
)
def test_design_checker_rejects_tampered_markdown(artifacts, mutate):
    data, md = artifacts
    assert checker.check_design_artifacts(data, mutate(md))


def _t10(d):
    return next(r for r in d["threat_matrix"] if r["id"] == "T-10")


@pytest.mark.parametrize(
    "mutate",
    [
        # T-10 drifting back to the noncanonical alias, in either column
        lambda d: _t10(d).update(expected_fail_closed_behavior=_t10(d)["expected_fail_closed_behavior"].replace("CEILING_EXCEEDED", "OUTSIDE_CEILING")),
        lambda d: _t10(d).update(test_strategy=_t10(d)["test_strategy"].replace("CEILING_EXCEEDED", "OUTSIDE_CEILING")),
        # any threat row naming a reason code the table does not define
        lambda d: d["threat_matrix"][41].update(expected_fail_closed_behavior="LINEAGE_DISCONTINUOUS"),
        lambda d: d["revocation_threat_matrix"][0].update(test_strategy="-> REVOKED_UPSTREAM"),
        # the table itself losing or redefining the ceiling code
        lambda d: d["reason_codes"].remove(next(r for r in d["reason_codes"] if r["code"] == "CEILING_EXCEEDED")),
        lambda d: next(r for r in d["reason_codes"] if r["code"] == "CEILING_EXCEEDED").update(meaning="Other"),
    ],
)
def test_design_checker_rejects_reason_code_drift_json(artifacts, mutate):
    data, md = artifacts
    tampered = copy.deepcopy(data)
    mutate(tampered)
    assert checker.check_design_artifacts(tampered, md)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m.replace("evaluate P5 action -> CEILING_EXCEEDED", "evaluate P5 action -> OUTSIDE_CEILING"),
        lambda m: m.replace("| CEILING_EXCEEDED; P5 is not issuable", "| OUTSIDE_CEILING; P5 is not issuable"),
        lambda m: m.replace("| `CEILING_EXCEEDED` |", "| `OUTSIDE_CEILING` |"),  # MD/JSON table drift
    ],
)
def test_design_checker_rejects_reason_code_drift_markdown(artifacts, mutate):
    data, md = artifacts
    tampered = mutate(md)
    assert tampered != md
    assert checker.check_design_artifacts(data, tampered)


def test_t10_reason_is_the_authoritative_ceiling_code(artifacts):
    """Design-contract consistency only; says nothing about runtime evaluation."""
    data, _ = artifacts
    codes = {r["code"]: r["meaning"] for r in data["reason_codes"]}
    assert codes[checker._T10_REASON_CODE] == "Required P-tier above effective ceiling"
    t10 = _t10(data)
    assert checker._T10_REASON_CODE in t10["expected_fail_closed_behavior"]
    assert checker._T10_REASON_CODE in t10["test_strategy"]
    assert "OUTSIDE_CEILING" not in json.dumps(data)


@pytest.mark.parametrize(
    "status_line",
    [
        "?? jarvis/delegation_engine.py",  # production code under another name/path
        " M app/decision_intelligence/permission_engine.py",
        "?? migrations/versions/abc123_delegation.py",
        # v0.2.5.1: the approved design is committed and may no longer change
        " M docs/V0_2_5_DELEGATION_AND_AUTHORITY_SECURITY_DESIGN.md",
        " M docs/v0.2.5_delegation_authority_design.json",
        # v0.2.5.1: only the exact contract/algebra files may exist in the package
        "?? app/authority_contracts/evaluator.py",
        "?? app/authority_contracts/store.py",
        # F04-D / F04-G: the historical flag authorizes no runtime path or later stage
        "?? app/delegation/__init__.py",
        "?? app/authority/__init__.py",
        "?? docs/V0_2_5_2_DELEGATION_RECORDS_AND_STORE.md",
        "?? tests/test_v0252_delegation_store.py",
        "?? docs/V0_2_6_CONTEXT_BROKER.md",
    ],
)
def test_changed_file_allowlist_rejects_other_files(monkeypatch, status_line):
    real_git = checker._git

    def fake_git(*args):
        if args[:2] == ("status", "--porcelain") and "-uall" in args:
            return status_line
        return real_git(*args)

    monkeypatch.setattr(checker, "_git", fake_git)
    assert any("allowlist" in p for p in checker.check_repository(_REPO_ROOT))


def test_design_approval_is_not_implementation_authorization(artifacts):
    data, _ = artifacts
    assert data["status"] == "DESIGN_ONLY"
    assert data["human_design_approval"] == "APPROVED" and data["design_approved"] is True
    for flag in checker._MUST_BE_FALSE:
        assert data[flag] is False
    decisions = {q["id"]: q["decision"] for q in data["design_approval_questions"]}
    assert decisions == checker._EXPECTED_DA_DECISIONS


def test_da03_hostile_checks_all_fail_closed(artifacts):
    data, _ = artifacts
    assert [c["id"] for c in data["da03_hostile_checks"]] == checker._DA03_CHECK_IDS
    assert {c["expected_result"] for c in data["da03_hostile_checks"]} == {"FAIL_CLOSED"}
    assert data["p5_boundary"]["p5_proposal_outcome"] == "STOP_AT_AUTHORIZATION_BOUNDARY"


@pytest.mark.parametrize(
    "rel_path,class_name,allowed",
    [
        # v0.2.5.1 contracts: only inside the authority_contracts package
        ("app/authority_contracts/contracts.py", "AuthorityScope", True),
        ("app/authority_contracts/contracts.py", "PrincipalRef", True),
        ("app/authority_contracts/contracts.py", "ObjectiveRef", True),
        ("app/decision_intelligence/schemas.py", "AuthorityScope", False),
        ("app/agent_identity/contracts.py", "PrincipalRef", False),
        ("app/providers/contracts.py", "PTier", False),
        ("app/security/objectives.py", "ObjectiveRef", False),
        # later-stage contracts: never, not even inside the package
        ("app/authority_contracts/contracts.py", "DelegationRecord", False),
        ("app/authority_contracts/contracts.py", "RootAuthorization", False),
        ("app/authority_contracts/algebra.py", "RedelegationPolicy", False),
        ("app/authority_contracts/algebra.py", "AuthorityEvaluation", False),
        ("app/authority_contracts/algebra.py", "DelegationStore", False),
        ("app/tools/engine.py", "AuthorityEngine", False),
    ],
)
def test_contract_class_placement(tmp_path, rel_path, class_name, allowed):
    target = tmp_path / rel_path
    target.parent.mkdir(parents=True)
    target.write_text(f"class {class_name}:\n    pass\n", encoding="utf-8")
    problems = checker._check_contract_class_placement(tmp_path)
    assert (problems == []) is allowed, problems


def test_v0251_package_may_exist_but_not_runtime_paths(monkeypatch):
    real_git = checker._git

    def fake_git(*args):
        if args[:2] == ("status", "--porcelain") and "-uall" in args:
            return "?? app/authority_contracts/contracts.py"
        if args[:2] == ("status", "--porcelain"):
            return "?? app/authority_contracts/"
        return real_git(*args)

    monkeypatch.setattr(checker, "_git", fake_git)
    problems = checker.check_repository(_REPO_ROOT)
    assert not any("allowlist" in p or "app/ or migrations/" in p for p in problems), problems


# --------------------------------------------------------------------------
# F-04: historical design-checkpoint flags vs the current phase allowance
# --------------------------------------------------------------------------

_V0251_PORCELAIN = "\n".join(
    (" M " if p.startswith(("scripts/", "tests/test_v025_")) else "?? ") + p
    for p in sorted(checker._ALLOWED_CHANGED_FILES)
)


def test_f04a_design_artifacts_equal_the_approved_commit():
    import subprocess

    for rel in (checker._MD_PATH, checker._JSON_PATH):
        # exit code 0 only if the working-tree content equals the committed blob
        result = subprocess.run(
            ["git", "diff", "--quiet", checker._APPROVED_DESIGN_COMMIT, "--", rel.as_posix()],
            cwd=_REPO_ROOT,
        )
        assert result.returncode == 0, rel


def test_f04b_historical_flag_does_not_block_the_exact_v0251_file_set(monkeypatch, artifacts):
    data, md = artifacts
    assert data["implementation_authorized"] is False  # historical, unchanged
    assert checker._CHECKPOINT_LINE in md
    assert checker.check_design_artifacts(data, md) == []
    real_git = checker._git

    def fake_git(*args):
        if args[:2] == ("status", "--porcelain") and "-uall" in args:
            return _V0251_PORCELAIN
        if args[:2] == ("status", "--porcelain"):
            return "?? app/authority_contracts/"
        return real_git(*args)

    monkeypatch.setattr(checker, "_git", fake_git)
    assert checker.check_repository(_REPO_ROOT) == []


@pytest.mark.parametrize("changed", [checker._MD_PATH.as_posix(), checker._JSON_PATH.as_posix()])
def test_f04f_design_artifact_change_rejected_even_when_committed(monkeypatch, changed):
    """A later commit that edits the design would leave `git status` clean;
    the content comparison against 1e242b8 still rejects it."""
    real_git = checker._git

    def fake_git(*args):
        if args[:2] == ("diff", "--name-only"):
            return changed
        return real_git(*args)

    monkeypatch.setattr(checker, "_git", fake_git)
    assert any("approved design artifacts differ" in p for p in checker.check_repository(_REPO_ROOT))


def test_f04d_forbidden_runtime_paths_rejected(tmp_path):
    for rel in checker._FORBIDDEN_PATHS:
        (tmp_path / rel).mkdir(parents=True)
    problems = checker.check_repository(tmp_path)
    for rel in ("app/delegation", "app/authority"):
        assert f"forbidden implementation path exists: {rel}" in problems


def test_f04_phase_record_is_present_and_narrow():
    doc = (_REPO_ROOT / checker._V0251_DOC_PATH).read_text(encoding="utf-8")
    assert checker.check_phase_record(doc) == []


@pytest.mark.parametrize("mutate", [
    # widening the authorized phase or dropping a NOT AUTHORIZED line fails
    lambda t: t.replace("v0.2.5.1 only (pure contracts + algebra)", "v0.2.5.1+ (all v0.2.5 stages)"),
    lambda t: re.sub(r"(?m)^(v0\.2\.5\.2\+ += )NOT AUTHORIZED$", r"\1AUTHORIZED", t),
    lambda t: re.sub(r"(?m)^v0\.2\.6 += NOT AUTHORIZED$", "", t),
    lambda t: re.sub(r"immutable\s+historical", "current", t),
])
def test_f04g_phase_record_widening_rejected(mutate):
    doc = (_REPO_ROOT / checker._V0251_DOC_PATH).read_text(encoding="utf-8")
    tampered = mutate(doc)
    assert tampered != doc
    assert checker.check_phase_record(tampered)


def test_git_output_keeps_leading_porcelain_status_column(monkeypatch):
    """F-02: stripping the whole output ate the leading space of the first
    porcelain line (" M path" -> "M path"), mis-parsing its path."""
    import subprocess

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout=" M scripts/check_v025_design_contract.py\n?? x.py\n")

    monkeypatch.setattr(checker.subprocess, "run", fake_run)
    assert checker._git("status", "--porcelain") == " M scripts/check_v025_design_contract.py\n?? x.py"


def test_forbidden_implementation_paths_absent():
    for rel in checker._FORBIDDEN_PATHS:
        assert not (_REPO_ROOT / rel).exists()
