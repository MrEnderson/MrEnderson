"""Decision & Action Intelligence (v0.1.3.1).

v0.1.2 gave Jarvis a deterministic gate on whether *research* was complete
enough to compare candidates (`app/research_intelligence/`). v0.1.3 extends
that same "never trust an LLM's own claim, verify deterministically"
philosophy one stage further down the pipeline:

    OBJECTIVE -> RESEARCH -> EVIDENCE READINESS -> DECISION -> DECISION GATE
    -> ACTION PLAN -> PERMISSION EVALUATION -> APPROVAL -> EXECUTION
    -> VERIFICATION -> RETRY / REPLAN -> QA -> EXECUTIVE REPORT

IMPLEMENTED IN v0.1.3.1 (this checkpoint):

- Domain contracts (`schemas.py`): Decision, ActionPlan, Action,
  ApprovalRequest, ExecutionResult, VerificationResult, PlanReadinessResult.
- Deterministic Decision lifecycle + Decision -> Plan boundary rules
  (`decision_rules.py`).
- Deterministic Action lifecycle state machine (`action_state_machine.py`).
- Deterministic structural dependency validation and plan readiness
  evaluation (`plan_validation.py`).
- Deterministic canonical action fingerprinting (`action_hash.py`).
- Deterministic retry/error-category classification (`retry_policy.py`).

NOT IMPLEMENTED YET (future v0.1.3.x checkpoints):

- Permission Engine (real permission evaluation against these Action
  contracts — today only app/security/permissions.py's existing
  agent-type-level check exists).
- Approval Engine (interactive approval handling for ApprovalRequest).
- Tool Registry (resolving Action.tool_name to a real callable).
- Real execution of any Action.
- Real verification adapters.
- Retry/replan execution (only classification helpers exist today).
- Any external action, email, publishing, spend, or shell/browser control.

Nothing in this package makes a live model or research-provider call, and
nothing here executes anything. See docs/architecture.md and
docs/decision_intelligence.md.
"""
