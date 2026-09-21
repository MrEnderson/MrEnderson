"""Static, non-destructive check of the v0.2.0 architecture/security contract
(docs/V0_2_ARCHITECTURE_AND_SECURITY_CONTRACT.md / docs/v0.2_architecture_security_contract.json).

Verifies, WITHOUT touching the database, `.env`, the network, credentials, or
any ToolAdapter/provider:

  - both contract artifacts exist;
  - the JSON contract is valid and internally consistent;
  - version/phase/predecessor fields match the expected frozen v0.1.3 baseline
    (predecessor commit/tag are cross-checked against `git`, a local
    read-only lookup only -- this script never writes to git);
  - the required security invariants and fail-closed conditions are present;
  - prohibited capabilities and the planned phase sequence are present;
  - the full set of boolean security expectations the contract makes about
    itself actually hold -- central authority, no authority laundering
    (including no cross-delegation union), no privacy-weakening fallback,
    credential isolation, context classification stickiness, approval
    binding, denial persistence, self-approval prohibition, coding-agent
    protected targets, self-improvement evaluator independence,
    multi-business tenant isolation, infrastructure/privacy policy
    invariance, atomic budget accounting, and audit record integrity.

This is a read-only validator. It does not modify files, the database, or
Git; it does not call external APIs, access the network, execute providers,
or invoke ToolAdapters; it requires no secrets.

Usage:
    python scripts/check_v020_contract.py

Exit code 0 = contract matches expectations. Exit code 1 = a discrepancy
was found (printed).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent

_REQUIRED_TOP_LEVEL_KEYS = [
    "version",
    "release_name",
    "phase",
    "predecessor_version",
    "predecessor_commit",
    "predecessor_tag",
    "architecture_status",
    "central_authority",
    "trust_boundaries",
    "provider_rules",
    "agent_rules",
    "delegation_rules",
    "authority_rules",
    "context_rules",
    "credential_rules",
    "provenance_rules",
    "invocation_rules",
    "budget_rules",
    "permission_compatibility",
    "fail_closed_conditions",
    "security_invariants",
    "prohibited_capabilities",
    "planned_phases",
    "approval_binding_rules",
    "denial_persistence_rules",
    "self_approval_rules",
    "coding_agent_rules",
    "self_improvement_rules",
    "multi_business_rules",
    "infrastructure_rules",
    "audit_integrity_rules",
    "hostile_review",
    "implementation_sensitive_requirements",
]

_REQUIRED_ISR_IDS = {"ISR-01", "ISR-02"}

_REQUIRED_FAIL_CLOSED_CONDITIONS = {
    "unknown_provider",
    "unknown_model",
    "unknown_agent",
    "unknown_capability",
    "missing_delegation",
    "expired_delegation",
    "invalid_authority_chain",
    "missing_context_authorization",
    "privacy_incompatibility",
    "budget_exhaustion",
    "malformed_structured_output",
    "unknown_tool_adapter",
    "missing_approval",
    "stale_approval",
    "approval_hash_mismatch",
    "tampered_invocation_or_result_records",
}

_REQUIRED_PROHIBITED_CAPABILITIES = {
    "unrestricted_shell",
    "unrestricted_browser",
    "email_sending",
    "publishing",
    "financial_execution",
    "autonomous_purchasing",
    "software_installation",
    "admin_or_root_access",
    "nas_administration",
    "autonomous_deployment",
    "autonomous_self_modification",
    "distributed_worker_infrastructure",
    "uncontrolled_agent_to_agent_execution",
    "new_external_side_effect_tool_adapters",
}

_REQUIRED_INVARIANT_IDS = {f"SI-{i:02d}" for i in range(1, 26)}

_REQUIRED_PLANNED_PHASES = {
    "v0.2.0", "v0.2.1", "v0.2.2", "v0.2.3", "v0.2.4", "v0.2.5",
    "v0.2.6", "v0.2.7", "v0.2.8", "v0.2.9", "v0.2.10", "v0.2_FREEZE",
}

_REQUIRED_PRESERVED_V013_COMPONENTS = {
    "research_evidence_readiness", "decision_gate", "permission_engine", "approval_engine",
    "budget_engine", "durable_executor", "tool_registry", "verification",
    "failure_intelligence", "retry", "replanning", "reconciliation",
    "crash_restart_recovery", "qa", "executive_reporting",
}

_REQUIRED_DENIAL_EVASION_PATTERNS = {
    "reframing", "splitting", "redelegation", "provider_switching",
    "waiting_or_retrying", "new_child_agent",
}

_REQUIRED_CODING_AGENT_PROTECTED_TARGETS = {
    "permission_engine", "approval_engine", "budget_engine",
    "architecture_or_security_contract", "compliance_validator_scripts",
    "security_invariant_tests", "migration_history", "frozen_release_artifacts",
}

_REQUIRED_APPROVAL_BOUND_FIELDS = {
    "recipient", "destination", "external_system", "quantity", "financial_amount",
    "content_hash", "requesting_agent", "scope",
}

_REQUIRED_CONTEXT_PERSISTENCE_POINTS = {"delegation", "transformation", "storage"}

# Dotted-path boolean/string expectations the contract makes about itself.
# Each entry: (dotted path, expected value, human-readable requirement).
_BOOLEAN_EXPECTATIONS: list[tuple[str, Any, str]] = [
    ("delegation_rules.may_increase_authority", False, "delegation cannot increase authority"),
    ("invocation_rules.model_output_direct_execution_allowed", False, "model output cannot directly execute"),
    ("budget_rules.model_budget_grants_external_financial_authority", False, "model budget cannot grant business spending authority"),
    ("budget_rules.hierarchical_budget_child_may_exceed_parent_delegation", False, "child budget cannot exceed parent delegation"),
    ("budget_rules.aggregate_child_delegation_may_exceed_parent_remaining_capacity", False, "aggregate child delegation cannot exceed parent's remaining capacity"),
    ("budget_rules.concurrent_overspend_prevention_required", True, "budget accounting must prevent concurrent overspend"),
    ("provider_rules.registration_grants_execution_authority", False, "registering a provider cannot grant execution authority"),
    ("provider_rules.fallback_may_weaken_privacy_or_permission_or_budget_policy", False, "provider fallback cannot weaken privacy/permission/budget policy"),
    ("agent_rules.role_or_title_grants_authority", False, "agent role/title cannot grant authority"),
    ("agent_rules.model_supplied_identity_claims_trusted", False, "model-supplied identity claims must be untrusted"),
    ("credential_rules.models_receive_raw_secrets", False, "models must never receive raw secrets"),
    ("provenance_rules.transformation_upgrades_trust", False, "transformation must never upgrade trust"),
    ("authority_rules.cross_delegation_union_allowed", False, "authority must not be unioned across simultaneous delegations"),
    ("authority_rules.single_delegation_lineage_per_action", True, "each action must resolve to exactly one delegation lineage"),
    ("authority_rules.no_authority_laundering.delegation_chains_increase_authority", False, "delegation chains cannot increase authority"),
    ("authority_rules.no_authority_laundering.replanning_increases_authority", False, "replanning cannot increase authority"),
    ("authority_rules.no_authority_laundering.retries_increase_authority", False, "retries cannot increase authority"),
    ("authority_rules.no_authority_laundering.provider_fallback_increases_authority", False, "provider fallback cannot increase authority"),
    ("authority_rules.no_authority_laundering.failure_recovery_increases_authority", False, "failure recovery cannot increase authority"),
    ("context_rules.default_full_memory_access_to_agents_or_providers", False, "agents/providers cannot receive full memory access by default"),
    ("context_rules.broader_scope_storage_without_reauthorization_allowed", False, "storage into a broader scope cannot skip re-authorization"),
    ("permission_compatibility.agent_title_overrides_permission_tier", False, "agent title cannot override a permission tier"),
    ("approval_binding_rules.material_mutation_invalidates_approval", True, "a material mutation must invalidate an existing approval"),
    ("approval_binding_rules.requires_reevaluation_on_mismatch", True, "an approval hash mismatch must require re-evaluation"),
    ("denial_persistence_rules.denied_action_record_required", True, "a denial must produce a durable denied-action record"),
    ("denial_persistence_rules.evasion_bypasses_denial", False, "no evasion pattern may bypass a recorded denial"),
    ("self_approval_rules.agent_may_approve_own_privileged_action", False, "an agent cannot approve its own privileged action"),
    ("self_approval_rules.parent_may_approve_child_action_requiring_human_approval", False, "a parent cannot substitute for required human approval"),
    ("self_approval_rules.qa_agent_may_satisfy_approval_requirement", False, "QA cannot satisfy an approval requirement"),
    ("self_approval_rules.role_title_implies_approval_authority", False, "a role title cannot imply approval authority"),
    ("self_approval_rules.provider_claimed_approval_trusted", False, "a provider's claim of approval must be untrusted"),
    ("coding_agent_rules.agent_may_modify_protected_targets_as_ordinary_change", False, "protected targets cannot be modified as an ordinary code change"),
    ("coding_agent_rules.protected_target_change_requires_distinct_human_gated_workflow", True, "protected-target changes require a distinct human-gated workflow"),
    ("coding_agent_rules.agent_may_modify_tests_to_make_own_change_pass", False, "an agent cannot modify tests to make its own change pass"),
    ("self_improvement_rules.candidate_may_modify_its_own_evaluator", False, "a self-improvement candidate cannot modify its own evaluator"),
    ("self_improvement_rules.deployment_requires_explicit_authorization_distinct_from_testing", True, "deployment requires authorization distinct from testing"),
    ("self_improvement_rules.self_labeled_deployment_as_testing_bypasses_gate", False, "relabeling deployment as testing cannot bypass the gate"),
    ("multi_business_rules.tenant_scope_is_explicit_authorization_dimension", True, "tenant scope must be an explicit authorization dimension"),
    ("multi_business_rules.relevance_ranking_can_substitute_for_authorization", False, "relevance ranking cannot substitute for tenant authorization"),
    ("multi_business_rules.simultaneous_multi_tenant_assignment_grants_combined_scope", False, "simultaneous multi-tenant assignment cannot grant combined scope"),
    ("infrastructure_rules.resource_scheduling_may_alter_permission_or_privacy_policy", False, "resource scheduling cannot alter permission/privacy policy"),
    ("infrastructure_rules.node_failure_permits_privacy_policy_override", False, "node failure cannot override privacy policy"),
    ("audit_integrity_rules.durable_records_mutable_after_write", False, "durable audit records must be append-only"),
    ("audit_integrity_rules.corrections_require_superseding_record", True, "corrections require a superseding record"),
    ("audit_integrity_rules.replay_or_duplicate_invocation_detection_required", True, "replay/duplicate invocation detection is required"),
    ("audit_integrity_rules.fabricated_or_dangling_lineage_fails_closed", True, "fabricated/dangling lineage must fail closed"),
    ("hostile_review.conducted", True, "a hostile review must have been conducted"),
    ("hostile_review.all_findings_remediated_or_registered", True, "every hostile-review finding must be remediated or explicitly registered"),
]


def _fail(problems: list[str], message: str) -> None:
    problems.append(message)


def _get_path(data: dict, dotted_path: str) -> Any:
    node: Any = data
    for part in dotted_path.split("."):
        if not isinstance(node, dict) or part not in node:
            return _MISSING
        node = node[part]
    return node


_MISSING = object()


def _git_read_only(*args: str) -> str | None:
    """Best-effort local, read-only `git` lookup. Never writes; returns None
    on any failure so the caller can degrade to a warning instead of a hard
    failure when git is unavailable in the running environment."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def main() -> int:
    problems: list[str] = []
    warnings: list[str] = []

    doc_path = _REPO_ROOT / "docs" / "V0_2_ARCHITECTURE_AND_SECURITY_CONTRACT.md"
    json_path = _REPO_ROOT / "docs" / "v0.2_architecture_security_contract.json"

    if not doc_path.exists():
        _fail(problems, f"Missing required contract document: {doc_path}")
    if not json_path.exists():
        _fail(problems, f"Missing required contract document: {json_path}")
        print("\n".join(problems))
        return 1

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _fail(problems, f"{json_path} is not valid JSON: {exc}")
        print("\n".join(problems))
        return 1

    for key in _REQUIRED_TOP_LEVEL_KEYS:
        if key not in data:
            _fail(problems, f"Contract JSON is missing required top-level key: {key!r}")

    if data.get("version") != "v0.2.0":
        _fail(problems, f"Contract version is {data.get('version')!r}, expected 'v0.2.0'")

    if data.get("predecessor_version") != "v0.1.3":
        _fail(
            problems,
            f"Contract predecessor_version is {data.get('predecessor_version')!r}, expected 'v0.1.3'",
        )
    if data.get("predecessor_tag") != "v0.1.3":
        _fail(
            problems,
            f"Contract predecessor_tag is {data.get('predecessor_tag')!r}, expected 'v0.1.3'",
        )

    predecessor_commit = data.get("predecessor_commit")
    tag_commit = _git_read_only("rev-list", "-n", "1", "v0.1.3")
    if tag_commit is None:
        warnings.append(
            "Could not resolve git tag 'v0.1.3' locally to cross-check predecessor_commit "
            "(git unavailable or tag missing) -- skipped, not a failure."
        )
    elif predecessor_commit != tag_commit:
        _fail(
            problems,
            f"Contract predecessor_commit is {predecessor_commit!r}, but tag 'v0.1.3' "
            f"resolves to {tag_commit!r}",
        )

    # --- central authority ---
    central_authority = data.get("central_authority", {})
    statement = central_authority.get("statement", "") if isinstance(central_authority, dict) else ""
    if "Jarvis" not in statement or "authority boundary" not in statement:
        _fail(problems, "central_authority.statement does not establish Jarvis as the authority boundary")

    # --- every declared boolean/string security expectation must actually hold ---
    for dotted_path, expected, requirement in _BOOLEAN_EXPECTATIONS:
        actual = _get_path(data, dotted_path)
        if actual is _MISSING:
            _fail(problems, f"Missing {dotted_path!r} (required: {requirement})")
        elif actual != expected:
            _fail(
                problems,
                f"{dotted_path!r} is {actual!r}, expected {expected!r} (required: {requirement})",
            )

    # --- required-set fields ---
    def _check_required_set(dotted_path: str, required: set[str], label: str) -> None:
        actual_value = _get_path(data, dotted_path)
        actual_set = set(actual_value) if isinstance(actual_value, list) else set()
        missing = required - actual_set
        if missing:
            _fail(problems, f"Missing required {label}: {sorted(missing)}")

    _check_required_set("fail_closed_conditions", _REQUIRED_FAIL_CLOSED_CONDITIONS, "fail_closed_conditions")
    _check_required_set("prohibited_capabilities", _REQUIRED_PROHIBITED_CAPABILITIES, "prohibited_capabilities")
    _check_required_set(
        "permission_compatibility.preserved_v0_1_3_components",
        _REQUIRED_PRESERVED_V013_COMPONENTS,
        "permission_compatibility.preserved_v0_1_3_components",
    )
    _check_required_set(
        "denial_persistence_rules.checked_against",
        _REQUIRED_DENIAL_EVASION_PATTERNS,
        "denial_persistence_rules.checked_against",
    )
    _check_required_set(
        "coding_agent_rules.protected_targets",
        _REQUIRED_CODING_AGENT_PROTECTED_TARGETS,
        "coding_agent_rules.protected_targets",
    )
    _check_required_set(
        "approval_binding_rules.bound_to",
        _REQUIRED_APPROVAL_BOUND_FIELDS,
        "approval_binding_rules.bound_to",
    )
    _check_required_set(
        "context_rules.classification_persists_through",
        _REQUIRED_CONTEXT_PERSISTENCE_POINTS,
        "context_rules.classification_persists_through",
    )

    # --- hostile review finding count self-consistency ---
    hostile_review = data.get("hostile_review", {})
    if isinstance(hostile_review, dict):
        finding_ids = hostile_review.get("finding_ids", [])
        finding_count = hostile_review.get("finding_count")
        if isinstance(finding_ids, list) and finding_count != len(finding_ids):
            _fail(
                problems,
                f"hostile_review.finding_count is {finding_count!r} but finding_ids has "
                f"{len(finding_ids)} entries -- these must match",
            )

    # --- implementation-sensitive requirements: present and not weakening the invariant ---
    isr_entries = data.get("implementation_sensitive_requirements", [])
    actual_isr_ids = {isr.get("id") for isr in isr_entries if isinstance(isr, dict)}
    missing_isr = _REQUIRED_ISR_IDS - actual_isr_ids
    if missing_isr:
        _fail(problems, f"Missing required implementation_sensitive_requirements ids: {sorted(missing_isr)}")
    for isr in isr_entries:
        if not isinstance(isr, dict):
            continue
        if isr.get("defers_or_weakens_invariant") is not False:
            _fail(
                problems,
                f"implementation_sensitive_requirements entry {isr.get('id')!r} must have "
                f"defers_or_weakens_invariant explicitly false (recording a requirement must "
                f"never be read as deferring or weakening it)",
            )

    # --- security invariants ---
    actual_invariant_ids = {
        inv.get("id") for inv in data.get("security_invariants", []) if isinstance(inv, dict)
    }
    missing_invariants = _REQUIRED_INVARIANT_IDS - actual_invariant_ids
    if missing_invariants:
        _fail(problems, f"Missing required security_invariants ids: {sorted(missing_invariants)}")

    # --- planned phase sequence ---
    actual_phases = {
        p.get("phase") for p in data.get("planned_phases", []) if isinstance(p, dict)
    }
    missing_phases = _REQUIRED_PLANNED_PHASES - actual_phases
    if missing_phases:
        _fail(problems, f"Missing required planned_phases: {sorted(missing_phases)}")

    if problems:
        print("v0.2.0 CONTRACT CHECK: DISCREPANCY FOUND")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("v0.2.0 CONTRACT CHECK: OK")
    print(f"  Version: {data.get('version')}")
    print(f"  Predecessor: {data.get('predecessor_tag')} ({data.get('predecessor_commit')})")
    print(f"  Security invariants: {len(actual_invariant_ids)}")
    print(f"  Boolean/string expectations checked: {len(_BOOLEAN_EXPECTATIONS)}")
    print(f"  Fail-closed conditions: {len(set(data.get('fail_closed_conditions', [])))}")
    print(f"  Prohibited capabilities: {len(set(data.get('prohibited_capabilities', [])))}")
    print(f"  Planned phases: {len(actual_phases)}")
    for w in warnings:
        print(f"  (warning) {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
