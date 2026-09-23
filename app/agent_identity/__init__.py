"""Agent Identity + Agent Registry (v0.2.4).

Implements `docs/V0_2_4_AGENT_IDENTITY_AND_REGISTRY_SECURITY_CONTRACT.md`:
durable logical Jarvis agent identities (`AgentDefinition`) and a
deterministic, in-memory identity/discovery-only registry
(`AgentRegistry`). Deliberately a NEW top-level package, separate from the
pre-existing `app.agents` package (an unrelated, executable, permission-
bearing v0.1.3 agent-dispatch system) -- see the contract doc's "Critical
architectural decision: module placement" section for why.

Central invariant: agent identity is not authority. Registering an
`AgentDefinition` grants zero execution capability, zero permission, zero
approval authority, and zero tool access. It answers "who is this
identity," never "what is this identity allowed to do."

NOT IMPLEMENTED in this phase (deliberately deferred, see the contract
doc): permission_ceiling, model_budget, external_spending_ceiling,
reports_to/delegation hierarchy, ToolAdapter references, multi-business
tenant enforcement, any identity lifecycle mutation mechanism, database
persistence, Agent Delegation / Authority Attenuation (v0.2.5)."""
