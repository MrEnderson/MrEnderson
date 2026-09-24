"""DESIGN CONTRACT TEST -- v0.2.5 Delegation + Authority Attenuation.

v0.2.5 is DESIGN_ONLY: no production delegation code exists. These tests
exercise ONLY the design artifacts and scripts/check_v025_design_contract.py.
They say nothing about runtime delegation behavior.
"""
from __future__ import annotations

import copy
import importlib.util
import json
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


def test_forbidden_implementation_paths_absent():
    for rel in checker._FORBIDDEN_PATHS:
        assert not (_REPO_ROOT / rel).exists()
