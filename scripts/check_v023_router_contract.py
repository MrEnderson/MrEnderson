"""Static, non-destructive check of the v0.2.3 provider-router security
contract (docs/V0_2_3_PROVIDER_ROUTER_SECURITY_CONTRACT.md /
docs/v0.2.3_provider_router_security_contract.json).

Verifies, WITHOUT touching the database, `.env`, the network, credentials,
or any ToolAdapter/provider:

  - both contract artifacts exist;
  - the JSON contract is valid and encodes the expected v0.2.3 invariants
    (no security scoring, no fallback chain, LOCAL_ONLY fails closed, no
    authority fields, no provider invocation, no registry mutation, ...);
  - the router production modules (`app/providers/router.py`,
    `app/providers/routing_contracts.py`) exist and, by AST inspection
    (not brittle string grepping), contain no call to `.generate(`,
    `.stream(`, `.register(`, or `.health_check(`, and import nothing from
    the ToolAdapter/permission/approval/executor/budget subsystems;
  - `ProviderRegistry.register()` still has no `replace` parameter (v0.2.2
    identity hardening was not reintroduced by this phase);
  - the v0.2.2 ToolAdapter inventory is still exactly
    `['file.create_sandboxed']` (no new ToolAdapter was added).

This is a read-only validator. It does not modify files, the database, or
Git; it does not call external APIs, access the network, execute providers,
or invoke ToolAdapters; it requires no secrets.

Usage:
    python scripts/check_v023_router_contract.py

Exit code 0 = contract matches expectations. Exit code 1 = a discrepancy
was found (printed).
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent

_EXPECTED_PREDECESSOR_COMMIT = "83678171c9d28981d1c415e566a8ff802a7ad0af"

_REQUIRED_TOP_LEVEL_KEYS = [
    "version",
    "predecessor_version",
    "predecessor_commit",
    "implementation_status",
    "central_invariant",
    "non_goals",
    "trust_classification",
    "hard_constraints",
    "optimization_policies",
    "prohibited_optimization_policies",
    "security_constraints_are_weighted_or_scored",
    "deterministic_tie_break",
    "tie_break_is_quality_judgment",
    "privacy_requirement_values",
    "provider_locality_values",
    "provider_locality_is_field_on_provider_definition",
    "unknown_locality_satisfies_local_only",
    "local_only_falls_back_to_cloud",
    "health_state_values",
    "health_unknown_represented_as_snapshot_absence",
    "health_self_declared_by_provider_output",
    "live_health_checks_in_this_phase",
    "degraded_eligible_by_default",
    "cost_type",
    "cost_source",
    "cost_reads_app_config_pricing",
    "cost_reads_environment",
    "zero_cost_treated_as_missing",
    "unknown_cost_with_ceiling_set_is_eligible",
    "provider_claimed_cost_affects_routing",
    "allow_deny_deny_dominates_allow",
    "unknown_id_in_allow_deny_can_broaden_eligibility",
    "capability_union_used",
    "capability_reuses_v022_effective_capabilities_function",
    "fallback_chain_implemented",
    "fallback_may_weaken_privacy_or_permission_or_budget_policy",
    "no_authority_fields",
    "selection_record_has_execute_or_authorize_method",
    "router_invokes_provider_generate",
    "router_invokes_provider_stream",
    "router_calls_health_check_method",
    "router_may_register_or_mutate_registry",
    "registry_replace_true_reintroduced",
    "router_may_mutate_request",
    "router_thread_safe",
    "router_overclaims_distributed_consistency",
    "new_tool_adapter_introduced",
    "permission_engine_modified",
    "approval_engine_modified",
    "budget_engine_modified",
    "network_calls_made",
    "reason_codes",
    "selection_status_values",
    "hostile_review",
    "deferred",
]

# Dotted-path boolean expectations the contract makes about itself -- every
# one of these MUST hold for the router to satisfy the central invariant
# ("may select computational capability, may never grant authority").
_BOOLEAN_EXPECTATIONS: list[tuple[str, Any, str]] = [
    ("security_constraints_are_weighted_or_scored", False, "hard constraints must never be scored/weighted"),
    ("tie_break_is_quality_judgment", False, "deterministic tie-break must not be a quality judgment"),
    ("provider_locality_is_field_on_provider_definition", False, "locality must not modify v0.2.2 ProviderDefinition"),
    ("unknown_locality_satisfies_local_only", False, "unknown locality must not satisfy LOCAL_ONLY"),
    ("local_only_falls_back_to_cloud", False, "LOCAL_ONLY must never fall back to cloud"),
    ("health_unknown_represented_as_snapshot_absence", True, "unknown health must be snapshot absence, not a trusted value"),
    ("health_self_declared_by_provider_output", False, "health must never come from provider/model output"),
    ("live_health_checks_in_this_phase", False, "v0.2.3 must not perform live health checks"),
    ("degraded_eligible_by_default", False, "DEGRADED must require explicit opt-in, not be eligible by default"),
    ("cost_reads_app_config_pricing", False, "router cost must be independent of app.config.pricing (token-based, env-dependent)"),
    ("cost_reads_environment", False, "router must not read os.environ/getenv for cost"),
    ("zero_cost_treated_as_missing", False, "zero cost is a legitimate known value, not 'missing'"),
    ("unknown_cost_with_ceiling_set_is_eligible", False, "unknown cost against a stated ceiling must fail closed"),
    ("provider_claimed_cost_affects_routing", False, "a provider's own cost claim must have zero routing effect"),
    ("allow_deny_deny_dominates_allow", True, "deny must dominate allow"),
    ("unknown_id_in_allow_deny_can_broaden_eligibility", False, "an unknown allow/deny id must never broaden eligibility"),
    ("capability_union_used", False, "capability must be provider ∩ model, never a union"),
    ("capability_reuses_v022_effective_capabilities_function", True, "router must reuse v0.2.2's effective_capabilities function"),
    ("fallback_chain_implemented", False, "v0.2.3 must not implement a multi-candidate fallback chain"),
    ("fallback_may_weaken_privacy_or_permission_or_budget_policy", False, "fallback must never weaken policy (matches v0.2.0 provider_rules)"),
    ("selection_record_has_execute_or_authorize_method", False, "ProviderSelectionRecord must not be executable/authorizable"),
    ("router_invokes_provider_generate", False, "router must never call provider.generate()"),
    ("router_invokes_provider_stream", False, "router must never call provider.stream()"),
    ("router_calls_health_check_method", False, "router must never call a live health_check() method"),
    ("router_may_register_or_mutate_registry", False, "router must be read-only with respect to the registry"),
    ("registry_replace_true_reintroduced", False, "v0.2.2 identity hardening must not be reintroduced/weakened"),
    ("router_may_mutate_request", False, "routing request must remain immutable"),
    ("router_thread_safe", False, "router must not overclaim thread-safety the registry doesn't have"),
    ("router_overclaims_distributed_consistency", False, "router must not overclaim distributed/transactional consistency"),
    ("new_tool_adapter_introduced", False, "v0.2.3 must not introduce a new ToolAdapter"),
    ("permission_engine_modified", False, "v0.2.3 must not modify the Permission Engine"),
    ("approval_engine_modified", False, "v0.2.3 must not modify the Approval Engine"),
    ("budget_engine_modified", False, "v0.2.3 must not modify the (business) Budget Engine"),
    ("network_calls_made", False, "v0.2.3 must make zero network calls"),
    ("lowest_cost_requires_known_cost_to_participate", True, "LOWEST_COST finding F-01: only known-cost candidates may win"),
    ("lowest_cost_can_silently_degrade_to_deterministic", False, "LOWEST_COST finding F-01: must never silently mislabel a non-cost-based pick as cost-based"),
    ("selection_result_records_actual_optimization_used", True, "finding F-05: result must record the optimization policy actually applied"),
    ("selection_result_records_actual_allow_degraded_health_used", True, "finding F-05: result must record allow_degraded_health actually applied"),
    ("selection_result_self_validates_status_selected_consistency", True, "finding F-03: status/selected consistency must be structurally enforced"),
    ("selection_result_rejects_duplicate_evaluations", True, "finding F-03: evaluations must be unique per (provider_id, model_id)"),
    ("candidate_evaluation_eligible_xor_has_reason_codes_enforced", True, "finding F-03: eligible must be structurally exclusive with reason_codes"),
    ("unrecognized_optimization_value_rejected_not_silently_accepted", True, "finding F-04: a non-OptimizationPolicy value must raise, never silently route"),
]

_EXPECTED_TOOL_ADAPTERS = ["file.create_sandboxed"]

_FORBIDDEN_IMPORT_SUBSTRINGS = (
    "tool_adapters", "tool_registry", "permission", "approval",
    "executor", "budget", "orchestrat",
)

_FORBIDDEN_CALL_NAMES = ("generate", "stream", "register", "health_check")


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


def _ast_forbidden_calls(source: str, module_label: str, problems: list[str]) -> None:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _FORBIDDEN_CALL_NAMES:
                _fail(
                    problems,
                    f"{module_label} calls forbidden method '.{node.func.attr}(' "
                    f"at line {node.lineno} -- router must never invoke a provider "
                    f"or mutate the registry",
                )


def _ast_forbidden_imports(source: str, module_label: str, problems: list[str]) -> None:
    tree = ast.parse(source)
    imported_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.append(node.module)
    for name in imported_names:
        lowered = name.lower()
        for forbidden in _FORBIDDEN_IMPORT_SUBSTRINGS:
            if forbidden in lowered:
                _fail(problems, f"{module_label} imports {name!r} (forbidden substring {forbidden!r})")


def main() -> int:
    problems: list[str] = []

    doc_path = _REPO_ROOT / "docs" / "V0_2_3_PROVIDER_ROUTER_SECURITY_CONTRACT.md"
    json_path = _REPO_ROOT / "docs" / "v0.2.3_provider_router_security_contract.json"

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

    if data.get("version") != "v0.2.3":
        _fail(problems, f"Contract version is {data.get('version')!r}, expected 'v0.2.3'")

    if data.get("predecessor_commit") != _EXPECTED_PREDECESSOR_COMMIT:
        _fail(
            problems,
            f"Contract predecessor_commit is {data.get('predecessor_commit')!r}, "
            f"expected {_EXPECTED_PREDECESSOR_COMMIT!r}",
        )

    for dotted_path, expected, requirement in _BOOLEAN_EXPECTATIONS:
        actual = _get_path(data, dotted_path)
        if actual is _MISSING:
            _fail(problems, f"Missing {dotted_path!r} (required: {requirement})")
        elif actual != expected:
            _fail(
                problems,
                f"{dotted_path!r} is {actual!r}, expected {expected!r} (required: {requirement})",
            )

    reason_codes = set(data.get("reason_codes", []))
    expected_reason_codes = {
        "PROVIDER_DISABLED", "PROVIDER_DENIED", "PROVIDER_NOT_ALLOWED",
        "CAPABILITY_MISMATCH", "LOCALITY_MISMATCH", "HEALTH_UNAVAILABLE",
        "HEALTH_UNKNOWN", "HEALTH_DEGRADED_NOT_ALLOWED", "COST_EXCEEDED",
        "COST_UNKNOWN",
    }
    missing_codes = expected_reason_codes - reason_codes
    if missing_codes:
        _fail(problems, f"Missing required reason_codes: {sorted(missing_codes)}")

    if set(data.get("privacy_requirement_values", [])) != {"CLOUD_ALLOWED", "LOCAL_ONLY"}:
        _fail(problems, "privacy_requirement_values must be exactly {'CLOUD_ALLOWED', 'LOCAL_ONLY'} (no 'ANY', no 'LOCAL_PREFERRED')")

    if "ANY" in data.get("privacy_requirement_values", []):
        _fail(problems, "'ANY' must not appear in privacy_requirement_values (redundant with CLOUD_ALLOWED)")

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
        if hostile_review.get("conducted") is not True:
            _fail(problems, "hostile_review.conducted must be true")

    # --- production module existence + AST-level forbidden call/import check ---
    router_path = _REPO_ROOT / "app" / "providers" / "router.py"
    contracts_path = _REPO_ROOT / "app" / "providers" / "routing_contracts.py"
    for path, label in ((router_path, "router.py"), (contracts_path, "routing_contracts.py")):
        if not path.exists():
            _fail(problems, f"Missing required v0.2.3 production module: {path}")
            continue
        source = path.read_text(encoding="utf-8")
        _ast_forbidden_calls(source, label, problems)
        _ast_forbidden_imports(source, label, problems)
        if "os.environ" in source or "getenv" in source:
            _fail(problems, f"{label} appears to read environment variables (forbidden for router cost/health)")

    # --- v0.2.2 identity hardening not reintroduced ---
    registry_path = _REPO_ROOT / "app" / "providers" / "registry.py"
    if registry_path.exists():
        registry_source = registry_path.read_text(encoding="utf-8")
        registry_tree = ast.parse(registry_source)
        for node in ast.walk(registry_tree):
            if isinstance(node, ast.FunctionDef) and node.name == "register":
                params = {a.arg for a in node.args.args + node.args.kwonlyargs}
                if "replace" in params:
                    _fail(problems, "ProviderRegistry.register() has a 'replace' parameter again -- v0.2.2 identity hardening was reintroduced")
    else:
        _fail(problems, f"Missing expected v0.2.2 module: {registry_path}")

    # --- ToolAdapter inventory unchanged ---
    try:
        sys.path.insert(0, str(_REPO_ROOT))
        from app.decision_intelligence.tool_adapters import build_default_adapter_registry

        adapters = sorted(build_default_adapter_registry().list_tool_names())
        if adapters != _EXPECTED_TOOL_ADAPTERS:
            _fail(problems, f"ToolAdapter inventory is {adapters!r}, expected {_EXPECTED_TOOL_ADAPTERS!r}")
    except ImportError as exc:
        _fail(problems, f"Could not import ToolAdapterRegistry to verify inventory: {exc}")

    # --- live behavioral smoke-check: actually exercise route_providers(),
    # never trust the JSON's self-reported booleans alone for the F-01/F-05
    # findings (checker-quality concern from the hostile review: a static
    # AST/JSON check alone cannot catch a semantic regression in the
    # LOWEST_COST/result-consistency logic) ---
    try:
        from decimal import Decimal

        from app.providers.contracts import ModelDefinition, ProviderCapability, ProviderDefinition
        from app.providers.fake_provider import FakeProvider
        from app.providers.registry import ProviderRegistry
        from app.providers.router import route_providers
        from app.providers.routing_contracts import (
            OptimizationPolicy,
            ProviderHealthSnapshot,
            HealthState,
            ProviderRoutingRequest,
            SelectionStatus,
        )

        smoke_registry = ProviderRegistry()
        smoke_registry.register(
            FakeProvider(definition=ProviderDefinition(
                provider_id="__v023_checker_probe__", display_name="probe", provider_type="FAKE",
                capabilities=frozenset({ProviderCapability.TEXT_GENERATION}),
            )),
            models=[ModelDefinition(
                model_id="m", provider_id="__v023_checker_probe__", display_name="m",
                capabilities=frozenset({ProviderCapability.TEXT_GENERATION}),
            )],
        )
        smoke_health = ProviderHealthSnapshot({"__v023_checker_probe__": HealthState.HEALTHY})
        smoke_request = ProviderRoutingRequest(required_capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))

        no_cost_result = route_providers(
            smoke_registry, smoke_request, health=smoke_health, optimization=OptimizationPolicy.LOWEST_COST,
        )
        if no_cost_result.status is not SelectionStatus.NO_ELIGIBLE_PROVIDER:
            _fail(problems, "LIVE CHECK FAILED (finding F-01 regression): LOWEST_COST with no known cost did not return NO_ELIGIBLE_PROVIDER")
        if no_cost_result.optimization is not OptimizationPolicy.LOWEST_COST or no_cost_result.allow_degraded_health is not False:
            _fail(problems, "LIVE CHECK FAILED (finding F-05 regression): ProviderSelectionResult did not record the actual optimization/allow_degraded_health used")

        try:
            route_providers(smoke_registry, smoke_request, optimization="BEST")  # type: ignore[arg-type]
            _fail(problems, "LIVE CHECK FAILED (finding F-04 regression): an unrecognized optimization value was silently accepted")
        except TypeError:
            pass
    except Exception as exc:  # pragma: no cover -- surface as a checker failure, not a crash
        _fail(problems, f"Live behavioral smoke-check could not run: {type(exc).__name__}: {exc}")

    if problems:
        print("v0.2.3 ROUTER CONTRACT CHECK: DISCREPANCY FOUND")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("v0.2.3 ROUTER CONTRACT CHECK: OK")
    print(f"  Version: {data.get('version')}")
    print(f"  Predecessor: {data.get('predecessor_version')} ({data.get('predecessor_commit')})")
    print(f"  Hard constraints: {len(data.get('hard_constraints', []))}")
    print(f"  Reason codes: {len(reason_codes)}")
    print(f"  Boolean expectations checked: {len(_BOOLEAN_EXPECTATIONS)}")
    print(f"  ToolAdapters: {_EXPECTED_TOOL_ADAPTERS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
