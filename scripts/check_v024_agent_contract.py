"""Static, non-destructive check of the v0.2.4 agent identity/registry
security contract (docs/V0_2_4_AGENT_IDENTITY_AND_REGISTRY_SECURITY_CONTRACT.md /
docs/v0.2.4_agent_identity_registry_security_contract.json).

Verifies, WITHOUT touching the database, `.env`, the network, credentials,
or any ToolAdapter/provider:

  - both contract artifacts exist;
  - the JSON contract is valid and encodes the expected v0.2.4 invariants
    (identity is not authority, no replace API, disabled cannot resurrect,
    reserved metadata keys rejected, no provider/model invocation, ...);
  - the production modules (`app/agent_identity/contracts.py`,
    `app/agent_identity/registry.py`) exist and, by AST inspection, contain
    no call to `.generate(`, `.stream(`, `.health_check(`, or
    `route_providers(`, and
    import nothing from the ToolAdapter/permission/approval/executor/budget
    subsystems, nor from `app.agents` (the pre-existing, unrelated,
    executable v0.1.3 agent-dispatch package -- a deliberate module
    boundary, see the contract doc);
  - `AgentRegistry.register()` has no `replace` parameter and no
    hidden overwrite/upsert/force/update_identity/set_definition method;
  - `AgentDefinition` has no permission/approval/authority-shaped field;
  - v0.2.2's `ProviderRegistry.register()` still has no `replace` parameter
    (v0.2.2 identity hardening not reintroduced by this phase);
  - the v0.2.2 ToolAdapter inventory is still exactly
    `['file.create_sandboxed']` (no new ToolAdapter was added);
  - live behavioral smoke checks actually exercise `AgentRegistry` rather
    than trusting the JSON's self-reported booleans alone.

This is a read-only validator. It does not modify files, the database, or
Git; it does not call external APIs, access the network, execute providers,
or invoke ToolAdapters; it requires no secrets.

Usage:
    python scripts/check_v024_agent_contract.py

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

_EXPECTED_PREDECESSOR_COMMIT = "7dbc719ece601513f0eec3f315955ad256a5f638"

_REQUIRED_TOP_LEVEL_KEYS = [
    "version",
    "predecessor_version",
    "predecessor_commit",
    "implementation_status",
    "central_invariant",
    "module_location",
    "module_location_not_app_agents",
    "non_goals",
    "identity_namespaces",
    "identity_namespaces_cross_lookup_exists",
    "identity_namespace_string_equality_implies_equivalence",
    "agent_definition_fields",
    "role_or_display_name_grants_authority",
    "role_is_enum",
    "title_to_permission_mapping_exists",
    "agent_id_case_sensitive",
    "agent_id_namespace_prefix_is_access_control_boundary",
    "metadata_reserved_keys_rejected_at_construction",
    "metadata_reserved_keys",
    "metadata_deep_frozen",
    "metadata_ever_read_for_authority",
    "provider_model_policy_is_enforced_here",
    "registry_operations",
    "registry_has_replace_parameter",
    "registry_has_hidden_replacement_api",
    "duplicate_agent_id_always_fails_closed",
    "get_active_is_separate_method_not_boolean_flag",
    "disabled_agent_erased_from_registry",
    "disabled_agent_can_become_active_via_metadata",
    "disabled_agent_can_become_active_via_reregistration",
    "enabled_field_grants_permission",
    "registration_grants_execution_authority",
    "registration_calls_provider_router",
    "registration_invokes_provider_or_model",
    "agent_definition_converts_to_permission_approval_or_execution",
    "deterministic_ordering",
    "registry_thread_safe",
    "registry_overclaims_distributed_consistency",
    "database_migration_required",
    "alembic_head_unchanged",
    "tool_adapter_inventory_unchanged",
    "permission_engine_modified",
    "approval_engine_modified",
    "budget_engine_modified",
    "executor_modified",
    "provider_router_modified",
    "validate_default_true_applied",
    "extra_forbid_applied",
    "model_copy_or_model_construct_used_in_production",
    "network_calls_made",
    "hostile_review",
    "deferred",
]

_BOOLEAN_EXPECTATIONS: list[tuple[str, Any, str]] = [
    ("module_location_not_app_agents", True, "must not be placed inside the executable app.agents package"),
    ("identity_namespaces_cross_lookup_exists", False, "provider/model/agent namespaces must not cross-lookup"),
    ("identity_namespace_string_equality_implies_equivalence", False, "matching strings across namespaces must not imply identity"),
    ("role_or_display_name_grants_authority", False, "role/display_name must carry zero authority"),
    ("role_is_enum", False, "role should remain a validated string, not a rigid enum"),
    ("title_to_permission_mapping_exists", False, "no CEO=>P5-style mapping may exist"),
    ("agent_id_case_sensitive", True, "agent_id must be case-sensitive, matching provider_id semantics"),
    ("agent_id_namespace_prefix_is_access_control_boundary", False, "a dot-namespace prefix must never be an access-control boundary"),
    ("metadata_reserved_keys_rejected_at_construction", True, "reserved security-shaped metadata keys must be rejected, not merely ignored"),
    ("metadata_deep_frozen", True, "metadata must be deep-frozen"),
    ("metadata_ever_read_for_authority", False, "metadata must never be read for authority"),
    ("provider_model_policy_is_enforced_here", False, "provider/model preferences must be descriptive only, never enforced in this phase"),
    ("registry_has_replace_parameter", False, "AgentRegistry.register() must not accept a replace parameter"),
    ("registry_has_hidden_replacement_api", False, "no upsert/overwrite/force/update_identity alternate path may exist"),
    ("duplicate_agent_id_always_fails_closed", True, "duplicate agent_id must be unconditionally rejected"),
    ("get_active_is_separate_method_not_boolean_flag", True, "get_active must be its own method, not an include_disabled flag"),
    ("disabled_agent_erased_from_registry", False, "disabling must not erase audit identity"),
    ("disabled_agent_can_become_active_via_metadata", False, "metadata must never flip enabled state"),
    ("disabled_agent_can_become_active_via_reregistration", False, "no resurrection via duplicate registration"),
    ("enabled_field_grants_permission", False, "enabled must be eligibility only, never a permission grant"),
    ("registration_grants_execution_authority", False, "registration must grant zero execution authority"),
    ("registration_calls_provider_router", False, "registration must never call the v0.2.3 router"),
    ("registration_invokes_provider_or_model", False, "registration must invoke zero providers/models"),
    ("agent_definition_converts_to_permission_approval_or_execution", False, "no conversion path to Permission/Approval/Execution may exist"),
    ("registry_thread_safe", False, "must not overclaim thread-safety the registry doesn't have"),
    ("registry_overclaims_distributed_consistency", False, "must not overclaim distributed/transactional consistency"),
    ("database_migration_required", False, "v0.2.4 must not require a migration"),
    ("alembic_head_unchanged", True, "Alembic head must remain unchanged"),
    ("tool_adapter_inventory_unchanged", True, "ToolAdapter inventory must remain unchanged"),
    ("permission_engine_modified", False, "must not modify the Permission Engine"),
    ("approval_engine_modified", False, "must not modify the Approval Engine"),
    ("budget_engine_modified", False, "must not modify the Budget Engine"),
    ("executor_modified", False, "must not modify the durable executor"),
    ("provider_router_modified", False, "must not modify the v0.2.3 Provider Router"),
    ("validate_default_true_applied", True, "AgentDefinition must set validate_default=True"),
    ("extra_forbid_applied", True, "AgentDefinition must set extra=forbid"),
    ("model_copy_or_model_construct_used_in_production", False, "production code must not use Pydantic bypass APIs"),
    ("network_calls_made", False, "v0.2.4 must make zero network calls"),
    ("metadata_json_shaped_values_only", True, "metadata must hold only JSON-shaped values (B-02)"),
    ("metadata_in_place_operators_blocked", True, "metadata containers must block |= and *= (B-03)"),
    ("agent_id_ascii_charset_enforced", True, "agent_id must be restricted to the ASCII charset (B-05)"),
    ("labels_reject_control_and_line_separator_chars", True, "role/display_name must not forge log lines (B-06)"),
    ("enabled_strict_bool", True, "enabled must not coerce 'yes'/1 (B-07)"),
    ("hide_input_in_errors", True, "rejected values must not be echoed into error text (B-08)"),
    ("registry_accepts_exact_type_only", True, "register() must reject AgentDefinition subclasses (B-01)"),
    ("registry_revalidates_and_pins_own_snapshot", True, "register() must re-validate and store its own snapshot (B-01)"),
]

_EXPECTED_TOOL_ADAPTERS = ["file.create_sandboxed"]

_FORBIDDEN_IMPORT_SUBSTRINGS = (
    "tool_adapters", "tool_registry", "permission", "approval",
    "executor", "budget", "orchestrat", "app.agents",
)

_FORBIDDEN_CALL_NAMES = ("generate", "stream", "health_check", "route_providers")


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
                _fail(problems, f"{module_label} calls forbidden method/function '.{node.func.attr}(' at line {node.lineno}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "route_providers":
                _fail(problems, f"{module_label} calls forbidden function 'route_providers(' at line {node.lineno}")


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

    doc_path = _REPO_ROOT / "docs" / "V0_2_4_AGENT_IDENTITY_AND_REGISTRY_SECURITY_CONTRACT.md"
    json_path = _REPO_ROOT / "docs" / "v0.2.4_agent_identity_registry_security_contract.json"

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

    if data.get("version") != "v0.2.4":
        _fail(problems, f"Contract version is {data.get('version')!r}, expected 'v0.2.4'")

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
            _fail(problems, f"{dotted_path!r} is {actual!r}, expected {expected!r} (required: {requirement})")

    reserved = set(data.get("metadata_reserved_keys", []))
    expected_reserved = {
        "permission", "approval", "authority", "authorized", "admin", "execute",
        "can_spend", "approved", "tool_access", "credential", "secret", "token",
        "api_key", "password", "private_key",
    }
    missing_reserved = expected_reserved - reserved
    if missing_reserved:
        _fail(problems, f"Missing required metadata_reserved_keys: {sorted(missing_reserved)}")

    hostile_review = data.get("hostile_review", {})
    if isinstance(hostile_review, dict):
        finding_ids = hostile_review.get("finding_ids", [])
        finding_count = hostile_review.get("finding_count")
        if isinstance(finding_ids, list) and finding_count != len(finding_ids):
            _fail(problems, f"hostile_review.finding_count is {finding_count!r} but finding_ids has {len(finding_ids)} entries")
        if hostile_review.get("conducted") is not True:
            _fail(problems, "hostile_review.conducted must be true")

    # --- production module existence + AST-level forbidden call/import check ---
    contracts_path = _REPO_ROOT / "app" / "agent_identity" / "contracts.py"
    registry_path = _REPO_ROOT / "app" / "agent_identity" / "registry.py"
    for path, label in ((contracts_path, "agent_identity/contracts.py"), (registry_path, "agent_identity/registry.py")):
        if not path.exists():
            _fail(problems, f"Missing required v0.2.4 production module: {path}")
            continue
        source = path.read_text(encoding="utf-8")
        _ast_forbidden_calls(source, label, problems)
        _ast_forbidden_imports(source, label, problems)
        if "os.environ" in source or "getenv" in source:
            _fail(problems, f"{label} appears to read environment variables")
        if "model_copy" in source or "model_construct" in source:
            _fail(problems, f"{label} uses a Pydantic bypass API in production code")

    # --- AgentRegistry.register() has no replace parameter, no hidden replacement API ---
    if registry_path.exists():
        registry_source = registry_path.read_text(encoding="utf-8")
        registry_tree = ast.parse(registry_source)
        forbidden_method_names = {"replace", "overwrite", "upsert", "force_register", "update_identity", "set_definition"}
        for node in ast.walk(registry_tree):
            if isinstance(node, ast.FunctionDef):
                if node.name == "register":
                    params = {a.arg for a in node.args.args + node.args.kwonlyargs}
                    if "replace" in params:
                        _fail(problems, "AgentRegistry.register() has a 'replace' parameter -- not permitted in v0.2.4")
                if node.name in forbidden_method_names:
                    _fail(problems, f"AgentRegistry exposes forbidden method {node.name!r}")

    # --- v0.2.2 identity hardening not reintroduced ---
    provider_registry_path = _REPO_ROOT / "app" / "providers" / "registry.py"
    if provider_registry_path.exists():
        provider_registry_source = provider_registry_path.read_text(encoding="utf-8")
        provider_registry_tree = ast.parse(provider_registry_source)
        for node in ast.walk(provider_registry_tree):
            if isinstance(node, ast.FunctionDef) and node.name == "register":
                params = {a.arg for a in node.args.args + node.args.kwonlyargs}
                if "replace" in params:
                    _fail(problems, "ProviderRegistry.register() has a 'replace' parameter again -- v0.2.2 identity hardening was reintroduced")
    else:
        _fail(problems, f"Missing expected v0.2.2 module: {provider_registry_path}")

    # --- ToolAdapter inventory unchanged ---
    try:
        sys.path.insert(0, str(_REPO_ROOT))
        from app.decision_intelligence.tool_adapters import build_default_adapter_registry

        adapters = sorted(build_default_adapter_registry().list_tool_names())
        if adapters != _EXPECTED_TOOL_ADAPTERS:
            _fail(problems, f"ToolAdapter inventory is {adapters!r}, expected {_EXPECTED_TOOL_ADAPTERS!r}")
    except ImportError as exc:
        _fail(problems, f"Could not import ToolAdapterRegistry to verify inventory: {exc}")

    # --- live behavioral smoke-check ---
    try:
        from app.agent_identity.contracts import AgentDefinition
        from app.agent_identity.registry import AgentRegistry, DuplicateAgentError, UnknownAgentError, DisabledAgentError

        registry = AgentRegistry()
        agent = AgentDefinition(agent_id="v024.checker.probe", display_name="Probe", role="PROBE")
        registry.register(agent)

        try:
            registry.register(AgentDefinition(agent_id="v024.checker.probe", display_name="Different", role="DIFFERENT"))
            _fail(problems, "LIVE CHECK FAILED: duplicate agent_id was accepted")
        except DuplicateAgentError:
            pass

        try:
            registry.get_active("v024.checker.does-not-exist")
            _fail(problems, "LIVE CHECK FAILED: unknown agent_id did not raise")
        except UnknownAgentError:
            pass

        disabled = AgentDefinition(agent_id="v024.checker.probe-disabled", display_name="Disabled", role="PROBE", enabled=False)
        registry.register(disabled)
        try:
            registry.get_active("v024.checker.probe-disabled")
            _fail(problems, "LIVE CHECK FAILED: disabled agent was returned by get_active()")
        except DisabledAgentError:
            pass
        registry.get("v024.checker.probe-disabled")  # must NOT raise -- audit lookup still works

        for hostile_key in ("permission", "Permission", "OPENAI_API_KEY", "enabled"):
            try:
                AgentDefinition(agent_id="p", display_name="P", role="R", metadata={hostile_key: "P5"})
                _fail(problems, f"LIVE CHECK FAILED: reserved/shadow metadata key {hostile_key!r} was accepted")
            except ValueError:
                pass

        # B-01: subclass smuggling and validation-bypass records never register.
        from pydantic import ConfigDict

        from app.agent_identity.registry import InvalidAgentError

        class _Smuggler(AgentDefinition):
            model_config = ConfigDict(frozen=True, extra="allow")

        forged = [
            _Smuggler(agent_id="v024.checker.smuggler", display_name="S", role="R", permission="P5"),
            AgentDefinition.model_construct(agent_id="bad\x00id", display_name="P", role="R", metadata={"approved": True}),
            agent.model_copy(update={"agent_id": "v024.checker.copy", "metadata": {"approved": True}}),
        ]
        for record in forged:
            try:
                registry.register(record)
                _fail(problems, f"LIVE CHECK FAILED: forged {type(record).__name__} record was registered")
            except InvalidAgentError:
                pass
        if registry.get("v024.checker.probe") is agent:
            _fail(problems, "LIVE CHECK FAILED: registry stored the caller's object instead of its own snapshot")

        # B-03: in-place operators cannot mutate frozen metadata.
        frozen_probe = AgentDefinition(agent_id="v024.checker.frozen", display_name="F", role="R", metadata={"k": [1]})
        for mutate in (lambda m: m.__ior__({"k": 2}), lambda m: m["k"].__imul__(2)):
            try:
                mutate(frozen_probe.metadata)
                _fail(problems, "LIVE CHECK FAILED: frozen metadata was mutated in place")
            except TypeError:
                pass
    except Exception as exc:  # pragma: no cover -- surface as a checker failure, not a crash
        _fail(problems, f"Live behavioral smoke-check could not run: {type(exc).__name__}: {exc}")

    if problems:
        print("v0.2.4 AGENT CONTRACT CHECK: DISCREPANCY FOUND")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("v0.2.4 AGENT CONTRACT CHECK: OK")
    print(f"  Version: {data.get('version')}")
    print(f"  Predecessor: {data.get('predecessor_version')} ({data.get('predecessor_commit')})")
    print(f"  Boolean expectations checked: {len(_BOOLEAN_EXPECTATIONS)}")
    print(f"  ToolAdapters: {_EXPECTED_TOOL_ADAPTERS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
