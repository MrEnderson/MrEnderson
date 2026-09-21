"""Vendor-neutral AI provider abstraction (v0.2.1 — Provider Abstraction).

Implements the seam described by `docs/V0_2_ARCHITECTURE_AND_SECURITY_CONTRACT.md`
§4-§14, §19-§21: a provider is a source of computation, never a source of
authority. Every `ProviderResponse` is untrusted data until it passes
through Jarvis's own validation and control plane (v0.1.3, `app/decision_intelligence/`)
— nothing in this package creates, mutates, or bypasses a Permission,
Approval, Action, ExecutionResult, or VerificationResult, and nothing here
invokes a ToolAdapter.

This package deliberately does NOT contain: real OpenAI/Anthropic HTTP
calls (that remains `app/agents/providers.py`'s existing, untouched seam),
provider routing/fallback (v0.2.3), Agent Identity/Delegation (v0.2.4-5),
the Context Broker (v0.2.6), the Credential Broker, or the durable
ModelInvocation audit chain (v0.2.7). See `docs/V0_2_1_PROVIDER_ABSTRACTION.md`
for what v0.2.1 actually implements and why it lives in its own top-level
package rather than under `app/orchestration/` (which is the v0.1.3
mission/task control loop, a different "orchestration" from this one).

IMPLEMENTED IN v0.2.1 (this checkpoint):

- Vendor-neutral identity contracts (`contracts.py`): ProviderCapability,
  ProviderDefinition, ModelDefinition, ProviderRequest, ProviderResponse,
  UsageInfo.
- Canonical request/response fingerprinting (`request_hash.py`), the same
  allowlist-hash pattern as `app/decision_intelligence/action_hash.py`.
- A normalized provider failure taxonomy (`failures.py`), with message
  redaction — never automatic retry.
- The minimal provider protocol (`protocol.py`) and an identity/discovery-
  only `ProviderRegistry` (`registry.py`).
- Request/response correlation checking (`correlation.py`) — a mismatched
  response cannot silently masquerade as the one that was requested.
- `FakeProvider` (`fake_provider.py`) — the only new provider
  implementation this phase authorizes: deterministic, offline, and
  credential-free, built specifically to attack this package's own trust
  boundary (see `tests/test_provider_security.py`).

NOT IMPLEMENTED YET (later, separately authorized phases):

- Real provider adapters behind this abstraction (OpenAI/Anthropic/local).
- Provider routing, fallback, or health orchestration (v0.2.3).
- Agent Identity, Agent Registry, Delegation, authority attenuation
  (v0.2.4-v0.2.5).
- Context Broker, Credential Broker (v0.2.6).
- Durable ModelInvocation persistence / AI budget accounting (v0.2.7).
- Multi-agent orchestration (v0.2.8).
"""
