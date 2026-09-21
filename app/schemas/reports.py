"""Executive report schema. Every claim must be labeled FACT / ASSUMPTION / RECOMMENDATION / UNKNOWN."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.evidence import EvidenceItem


class AgentUsageBreakdown(BaseModel):
    agent_type: str
    provider: str
    model: str
    api_calls: int = 0
    initial_calls: int = 0
    retry_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class MissionUsage(BaseModel):
    """USAGE is always real (from the provider). estimated_cost_usd is only
    ever populated when pricing was explicitly configured for the models
    used — see app/config/pricing.py. `pricing_configured=False` means the
    total is unknown, never zero."""

    by_agent: list[AgentUsageBreakdown] = Field(default_factory=list)
    total_api_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_retries: int = 0
    elapsed_seconds: float | None = None
    estimated_cost_usd: float | None = None
    pricing_configured: bool = False
    budget_stopped_reason: str | None = None


class ExecutiveReport(BaseModel):
    objective: str
    status: str
    what_was_done: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    evidence_details: list[EvidenceItem] = Field(
        default_factory=list,
        description=(
            "The real EvidenceItems behind this mission's recommendation — cited ones "
            "(StrategyOutput.evidence_used) preferred, otherwise every item collected. "
            "The primary human-facing evidence representation; `evidence` above is kept "
            "for backward compatibility. UUIDs stay on each item for traceability only."
        ),
    )
    recommendation: str
    rejected_evidence_count: int = Field(
        default=0,
        description=(
            "Evidence gathered but excluded from evidence_details/key_findings because it "
            "scored REJECT relevance (off-topic/too generic) or was REJECTED by the Evidence "
            "Admission Gate (v0.1.2.4) — never silently deleted, just not mixed into business "
            "findings. See docs/research_intelligence.md."
        ),
    )
    rejected_evidence_reasons: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "v0.1.2.4 Phase 7: short reason-category -> count breakdown for "
            "rejected_evidence_count, so the report can say WHY evidence was excluded (e.g. "
            "INSUFFICIENT_CANDIDATE_OVERLAP, SOURCE_UNSUITABLE_FOR_REQUIREMENT) rather than "
            "just a bare number."
        ),
    )
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(
        default_factory=list,
        description=(
            "v0.1.2.6 Phase 9: actual research/business questions ONLY — see "
            "unresolved_evidence_gaps/qa_notes/unsupported_claims below for what used to be "
            "mixed in here."
        ),
    )
    unresolved_evidence_gaps: list[str] = Field(
        default_factory=list,
        description="Structured missing-evidence requirements (v0.1.2.6 Phase 9) — never resolved yet.",
    )
    qa_notes: list[str] = Field(
        default_factory=list,
        description="Bounded QA observations (v0.1.2.6 Phase 9) — never a full raw QA response.",
    )
    unsupported_claims: list[str] = Field(
        default_factory=list,
        description="Deterministic unsupported-claim warnings (v0.1.2.6 Phase 9).",
    )
    next_actions: list[str] = Field(default_factory=list)
    approvals_required: list[str] = Field(default_factory=list)
    usage: MissionUsage | None = None
    usage_role_breakdown: list[str] = Field(
        default_factory=list,
        description=(
            "v0.1.2.6 Phase 10: per-task worker-vs-QA model-call split — e.g. 'Research "
            "\"Validate candidates\": worker model calls: 8, QA evaluator calls: 8'. Task-level "
            "usage attribution (MissionUsage.by_agent, keyed by agent_type) is UNCHANGED and "
            "remains intentional; this is additional, finer-grained visibility, not a "
            "replacement. See app/agents/usage.py::ModelUsage.role."
        ),
    )
    comparison_ready: bool | None = Field(
        default=None,
        description=(
            "v0.1.2 Candidate Completeness Gate verdict from the final Strategy output. None "
            "when the mission wasn't a multi-candidate comparison. See "
            "app/research_intelligence/completeness.py."
        ),
    )
    evidence_coverage: list[str] = Field(
        default_factory=list, description="Per-candidate coverage summary lines (v0.1.2)."
    )
    critical_gaps: list[str] = Field(
        default_factory=list, description="Critical missing requirements blocking comparison (v0.1.2)."
    )
    other_material_gaps: list[str] = Field(
        default_factory=list,
        description=(
            "v0.1.2.4 Defect 4: materially deficient requirements that aren't CRITICAL — shown "
            "distinctly so a WEAK/PARTIAL critical category or a MISSING non-critical one is "
            "never silently absent from the report just because it isn't in critical_gaps."
        ),
    )
    next_research: list[str] = Field(
        default_factory=list, description="Prioritized remediation queries (v0.1.2)."
    )

    def to_text(self) -> str:
        def section(title: str, items: list[str]) -> str:
            body = "\n".join(f"  - {i}" for i in items) if items else "  (none)"
            return f"{title}:\n{body}"

        # A recommendation already framed as "DECISION STATUS: ..." (see
        # app/agents/strategy.py::_enforce_insufficient_evidence_framing)
        # speaks for itself — a generic "RECOMMENDATION:" prefix in front of
        # it would read as if a confident recommendation followed.
        recommendation_line = (
            self.recommendation
            if self.recommendation.strip().upper().startswith("DECISION STATUS:")
            else f"RECOMMENDATION: {self.recommendation}"
        )

        parts = [
            f"OBJECTIVE: {self.objective}",
            f"STATUS: {self.status}",
            section("WHAT WAS DONE", self.what_was_done),
            section("KEY FINDINGS", self.key_findings),
            self._evidence_section(),
            recommendation_line,
        ]
        if self.comparison_ready is not None:
            parts.append(
                f"COMPARISON READINESS: {'READY' if self.comparison_ready else 'NOT READY'}"
            )
        if self.evidence_coverage:
            parts.append(section("EVIDENCE COVERAGE", self.evidence_coverage))
        if self.critical_gaps:
            parts.append(section("CRITICAL GAPS", self.critical_gaps))
        if self.other_material_gaps:
            parts.append(section("OTHER MATERIAL GAPS", self.other_material_gaps))
        parts.extend(
            [
                section("RISKS", self.risks),
                section("ASSUMPTIONS", self.assumptions),
                section("OPEN QUESTIONS", self.open_questions),
            ]
        )
        # v0.1.2.6 Phase 9: only shown when non-empty — a GENERAL-mode
        # mission with no unresolved gaps/QA flags/unsupported claims
        # shouldn't print three empty sections.
        if self.unresolved_evidence_gaps:
            parts.append(section("UNRESOLVED EVIDENCE GAPS", self.unresolved_evidence_gaps))
        if self.qa_notes:
            parts.append(section("QA NOTES", self.qa_notes))
        if self.unsupported_claims:
            parts.append(section("UNSUPPORTED CLAIMS", self.unsupported_claims))
        if self.next_research:
            parts.append(section("NEXT RESEARCH", self.next_research))
        parts.extend(
            [
                section("NEXT ACTIONS", self.next_actions),
                section("APPROVALS REQUIRED", self.approvals_required),
            ]
        )
        if self.usage is not None:
            parts.append(self._usage_section(self.usage))
        if self.usage_role_breakdown:
            parts.append(section("USAGE BY MODEL-CALL ROLE", self.usage_role_breakdown))
        return "\n\n".join(parts)

    def _evidence_section(self) -> str:
        if not self.evidence_details:
            body = "\n".join(f"  - {i}" for i in self.evidence) if self.evidence else "  (none)"
            return f"EVIDENCE:\n{body}"

        lines = ["EVIDENCE:"]
        for i, e in enumerate(self.evidence_details, start=1):
            verification = (
                e.verification_status.value
                if hasattr(e.verification_status, "value")
                else str(e.verification_status)
            )
            lines.append(f"  [{i}] Claim: {e.claim}")
            lines.append(f"      Source: {e.source_title or '(untitled)'}")
            lines.append(f"      Publisher/domain: {e.publisher or 'unknown'}")
            lines.append(f"      URL: {e.source_url or 'unknown'}")
            lines.append(f"      Evidence depth: {e.evidence_depth}")
            lines.append(f"      Source quality: {e.source_quality}")
            # Source ROLE (v0.1.2 Research Intelligence — PRIMARY/
            # AUTHORITATIVE/COMMERCIAL_RESEARCH/MARKETPLACE/COMMUNITY/
            # DISCOVERY/UNKNOWN) is a richer, claim-suitability-aware
            # classification than the older source_quality field above,
            # which only recognizes gov/edu/community domains and leaves
            # every legitimate vendor/marketplace domain as UNKNOWN. Shown
            # alongside it, never as a replacement, for audit continuity.
            lines.append(f"      Source role: {e.source_role}")
            lines.append(f"      Retrieved: {e.retrieved_at.isoformat()}")
            lines.append(f"      Verification: {verification}")
            lines.append(f"      (id: {e.id})")
        if self.rejected_evidence_count:
            reason_summary = (
                " (" + ", ".join(f"{reason}: {count}" for reason, count in self.rejected_evidence_reasons.items()) + ")"
                if self.rejected_evidence_reasons
                else ""
            )
            lines.append(
                f"  REJECTED / OFF-TOPIC EVIDENCE: {self.rejected_evidence_count} item(s) excluded"
                f"{reason_summary} — never deleted, see audit trail for detail"
            )
        return "\n".join(lines)

    @staticmethod
    def _usage_section(usage: MissionUsage) -> str:
        lines = ["MISSION USAGE:"]
        for row in usage.by_agent:
            lines.append(
                f"  {row.agent_type.capitalize()} ({row.provider}/{row.model}): "
                f"{row.api_calls} calls (initial {row.initial_calls}, retries {row.retry_calls}), "
                f"{row.input_tokens} in / {row.output_tokens} out / {row.total_tokens} total tokens"
            )
        lines.append(f"  Retries: {usage.total_retries}")
        lines.append(f"  Total API calls: {usage.total_api_calls}")
        lines.append(f"  Total input tokens: {usage.total_input_tokens}")
        lines.append(f"  Total output tokens: {usage.total_output_tokens}")
        lines.append(f"  Total tokens: {usage.total_tokens}")
        if usage.elapsed_seconds is not None:
            lines.append(f"  Elapsed time: {usage.elapsed_seconds:.1f}s")
        if usage.pricing_configured and usage.estimated_cost_usd is not None:
            lines.append(f"  Estimated cost: ${usage.estimated_cost_usd:.4f}")
        else:
            lines.append("  Estimated cost: (pricing not configured)")
        if usage.budget_stopped_reason:
            lines.append(f"  STOPPED EARLY: {usage.budget_stopped_reason}")
        return "\n".join(lines)
