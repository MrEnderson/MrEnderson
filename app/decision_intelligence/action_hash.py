"""Canonical Action fingerprinting (spec section 9). An ApprovalRequest
must bind to the EXACT action payload it approved — this is how.

Fields included (security-relevant execution payload — anything whose
change should invalidate a prior approval):

- action_type
- tool_name
- inputs
- expected_result   (the claimed external effect)
- permission_level
- risk_level

Fields deliberately EXCLUDED (volatile lifecycle metadata — changing these
must NOT invalidate an approval for the same intended action):

- id, action_plan_id, sequence, dependencies
- status, started_at, completed_at, result, error
- retry_count, max_retries, approval_id, estimated_cost
- title, description, success_criteria, verification_method, agent_type

`estimated_cost`/`title`/`description` are explicitly left out: they can
change (e.g. a cost re-estimate, a copy edit) without changing what the
action actually DOES. `dependencies` is left out too — reordering when an
action runs relative to its plan siblings doesn't change the action's own
effect. If a genuinely security-relevant field is ever added to Action, it
must be added to `_HASHED_FIELDS` explicitly — this is an allowlist, not a
denylist, precisely so a new field defaults to NOT affecting approvals
until someone deliberately decides it should.
"""
from __future__ import annotations

import hashlib
import json

from app.decision_intelligence.schemas import Action

_HASHED_FIELDS = (
    "action_type",
    "tool_name",
    "inputs",
    "expected_result",
    "permission_level",
    "risk_level",
)


def canonical_action_payload(action: Action) -> dict:
    """The exact dict that gets hashed — exposed separately so tests (and
    future callers) can assert on it directly rather than only on the
    opaque digest."""
    dumped = action.model_dump(mode="json")
    return {field: dumped[field] for field in _HASHED_FIELDS}


def compute_action_hash(action: Action) -> str:
    """SHA-256 hex digest of the canonical payload. `sort_keys=True`
    recursively sorts nested dict keys too (e.g. within `inputs`), so
    dictionary key ordering never affects the result."""
    payload = canonical_action_payload(action)
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
