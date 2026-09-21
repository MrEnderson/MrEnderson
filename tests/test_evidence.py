"""Evidence schema, ResearchAgent grounding, deterministic evidence-QA checks,
and evidence persistence. All offline — MockProvider + MockResearchProvider,
no network, no live API key."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.agents.providers import MockProvider
from app.agents.research import ResearchAgent
from app.database.models import EvidenceVerificationStatus
from app.schemas.agents import AgentDescriptor, ResearchOutput, StrategyOption, StrategyOutput
from app.schemas.evidence import EvidenceItem
from app.security.evidence_qa import evaluate_evidence, merge_into_verdict
from app.tools.research_tools import MockResearchProvider


def _descriptor(name: str, model: str = "mock-model") -> AgentDescriptor:
    from app.database.models import PermissionLevel

    return AgentDescriptor(
        name=name,
        role=name,
        description=name,
        capabilities=[],
        permissions=[PermissionLevel.READ],
        model=model,
    )


# --- Schema -------------------------------------------------------------


def test_evidence_item_defaults():
    item = EvidenceItem(claim="X grew 10% in 2025")
    assert item.id
    assert item.retrieved_at.tzinfo is not None
    assert item.verification_status == EvidenceVerificationStatus.RETRIEVED
    assert 0.0 <= item.confidence <= 1.0


def test_research_output_separates_evidence_from_findings():
    output = ResearchOutput(
        question="q",
        findings=[],
        evidence=[EvidenceItem(claim="c", source_url="https://example.com/a")],
        assumptions=["a1"],
        unsupported_claims=["u1"],
        open_questions=["oq1"],
        summary="s",
    )
    assert len(output.evidence) == 1
    assert output.unsupported_claims == ["u1"]
    assert output.open_questions == ["oq1"]


# --- ResearchAgent grounding ---------------------------------------------


async def test_research_agent_with_mock_research_provider_attaches_real_evidence():
    agent = ResearchAgent(
        descriptor=_descriptor("research"),
        provider=MockProvider(),
        research_provider=MockResearchProvider(),
    )
    result = await agent.run(
        title="Research: children's colouring books", description="", input_data={}, context={}
    )
    assert isinstance(result, ResearchOutput)
    assert result.evidence, "expected evidence attached from the mock provider's search results"
    for item in result.evidence:
        assert item.source_url is not None
        assert item.verification_status == EvidenceVerificationStatus.MOCK
        assert item.query_used


async def test_research_agent_without_live_provider_matches_v01_behavior():
    """Default (DevResearchProvider) path must be unchanged from v0.1: no
    evidence gathered, MockProvider's dev/sample-data findings unaffected."""
    agent = ResearchAgent(descriptor=_descriptor("research"), provider=MockProvider())
    result = await agent.run(
        title="Research: example market", description="", input_data={}, context={}
    )
    assert result.evidence == []
    assert result.insufficient_evidence is True


# --- Deterministic evidence QA checks -------------------------------------


def test_evidence_qa_flags_fact_finding_with_no_evidence():
    output = ResearchOutput(
        question="q",
        findings=[{"claim": "X is true", "evidence_type": "FACT", "confidence": 0.9}],
        evidence=[],
        summary="s",
    ).model_dump(mode="json")

    check = evaluate_evidence(output)
    assert check.needs_review is True
    assert any("FACT" in issue for issue in check.issues)


def test_evidence_qa_passes_fact_finding_backed_by_evidence():
    output = ResearchOutput(
        question="q",
        findings=[{"claim": "X is true", "evidence_type": "FACT", "confidence": 0.9}],
        evidence=[EvidenceItem(claim="X is true", source_url="https://example.com/x")],
        summary="s",
    ).model_dump(mode="json")

    check = evaluate_evidence(output)
    assert check.needs_review is False


def test_evidence_qa_flags_excessive_duplicate_sources():
    dup_url = "https://example.com/same"
    output = ResearchOutput(
        question="q",
        findings=[],
        evidence=[EvidenceItem(claim=f"claim {i}", source_url=dup_url) for i in range(4)],
        summary="s",
    ).model_dump(mode="json")

    check = evaluate_evidence(output)
    assert check.needs_review is True
    assert any("duplicated" in issue for issue in check.issues)


def test_evidence_qa_flags_stale_evidence():
    old_date = datetime.now(timezone.utc) - timedelta(days=1000)
    output = ResearchOutput(
        question="q",
        findings=[],
        evidence=[
            EvidenceItem(
                claim="old stat", source_url="https://example.com/old", published_at=old_date
            )
        ],
        summary="s",
    ).model_dump(mode="json")

    check = evaluate_evidence(output)
    assert check.needs_review is True
    assert any("stale" in issue for issue in check.issues)


def test_evidence_qa_flags_unbacked_quantitative_strategy_claim():
    output = StrategyOutput(
        options_considered=[StrategyOption(name="A")],
        recommendation="The market size is $50 million and growing at 20% per year.",
        reasoning="Because it looked promising.",
        assumptions=["general market conditions hold"],
    ).model_dump(mode="json")

    check = evaluate_evidence(output)
    assert check.needs_review is True
    assert check.unsupported_claims


def test_evidence_qa_accepts_quantitative_claim_with_strong_evidence_used():
    output = StrategyOutput(
        options_considered=[StrategyOption(name="A")],
        recommendation="The market size is $50 million.",
        reasoning="Backed by cited evidence.",
        assumptions=["general market conditions hold"],
        evidence_used=["ev-1"],
    ).model_dump(mode="json")

    check = evaluate_evidence(
        output,
        input_data={
            "research_results": [
                {"evidence": [{"id": "ev-1", "evidence_depth": "PAGE_EXTRACT", "source_quality": "UNKNOWN"}]}
            ]
        },
    )
    assert check.needs_review is False


def test_evidence_qa_flags_quantitative_claim_backed_only_by_weak_evidence():
    """Phase 7 source-claim quality guard: a quantitative/financial claim
    citing evidence at all must not rely solely on UNKNOWN-quality
    SEARCH_SNIPPET evidence — see app/security/evidence_qa.py::_check_strategy."""
    output = StrategyOutput(
        options_considered=[StrategyOption(name="A")],
        recommendation="The market size is $50 million.",
        reasoning="Backed by cited evidence.",
        assumptions=["general market conditions hold"],
        evidence_used=["ev-1"],
    ).model_dump(mode="json")

    check = evaluate_evidence(
        output,
        input_data={
            "research_results": [
                {"evidence": [{"id": "ev-1", "evidence_depth": "SEARCH_SNIPPET", "source_quality": "UNKNOWN"}]}
            ]
        },
    )
    assert check.needs_review is True
    assert any("UNKNOWN-quality" in issue for issue in check.issues)


def test_evidence_qa_weak_evidence_guard_never_discards_the_evidence():
    """The weak evidence is flagged for review, not thrown away — it's still
    a real cited source, just not enough on its own for a high-confidence
    quantitative conclusion."""
    output = StrategyOutput(
        options_considered=[StrategyOption(name="A")],
        recommendation="Revenue grew to $5 million last year.",
        reasoning="Backed by a blog post.",
        assumptions=["a"],
        evidence_used=["ev-1"],
    ).model_dump(mode="json")

    check = evaluate_evidence(
        output,
        input_data={
            "research_results": [
                {"evidence": [{"id": "ev-1", "evidence_depth": "SEARCH_SNIPPET", "source_quality": "UNKNOWN"}]}
            ]
        },
    )
    assert check.needs_review is True
    # evidence_used itself is untouched — the guard flags, never deletes.
    assert output["evidence_used"] == ["ev-1"]


def test_evidence_qa_flags_evidence_used_id_not_in_research_results():
    output = StrategyOutput(
        options_considered=[StrategyOption(name="A")],
        recommendation="Plain recommendation with no numbers.",
        reasoning="r",
        assumptions=["a"],
        evidence_used=["missing-id"],
    ).model_dump(mode="json")

    check = evaluate_evidence(output, input_data={"research_results": [{"evidence": []}]})
    assert check.needs_review is True
    assert any("unknown evidence id" in issue for issue in check.issues)


def test_merge_into_verdict_downgrades_pass_to_needs_review():
    from app.schemas.agents import QAVerdict

    verdict = QAVerdict(verdict="PASS", score=0.9, feedback="looks good")
    check = evaluate_evidence(
        ResearchOutput(
            question="q",
            findings=[{"claim": "X", "evidence_type": "FACT", "confidence": 0.9}],
            evidence=[],
            summary="s",
        ).model_dump(mode="json")
    )
    merged = merge_into_verdict(verdict, check)
    assert merged.verdict == "NEEDS_REVIEW"
    assert "Evidence gap" in merged.feedback


def test_merge_into_verdict_is_noop_when_no_issues():
    from app.schemas.agents import QAVerdict

    verdict = QAVerdict(verdict="PASS", score=0.9, feedback="looks good")
    check = evaluate_evidence({"actions_performed": []})
    merged = merge_into_verdict(verdict, check)
    assert merged is verdict


# --- Strategy receives evidence --------------------------------------------


async def test_strategy_agent_receives_research_evidence_in_input():
    """StrategyAgent doesn't need a code change to receive evidence — it
    flows through automatically because ResearchOutput.model_dump() now
    includes `evidence`, and AgentExecutor._build_input passes the full
    dependency output dict into `research_results`. This asserts that
    contract holds end-to-end through the agent, not just the schema."""
    from app.agents.strategy import StrategyAgent

    class _EvidenceCheckingProvider:
        name = "check"

        async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
            import json

            payload = json.loads(user_prompt)
            research_results = payload["research_results"]
            assert research_results[0]["evidence"][0]["source_url"] == "https://example.com/1"
            return StrategyOutput(
                options_considered=[StrategyOption(name="A")],
                recommendation="ok",
                reasoning="because evidence was visible",
                assumptions=["a"],
            )

    agent = StrategyAgent(descriptor=_descriptor("strategy"), provider=_EvidenceCheckingProvider())
    research_output = ResearchOutput(
        question="q",
        findings=[],
        evidence=[EvidenceItem(claim="c", source_url="https://example.com/1")],
        summary="s",
    ).model_dump(mode="json")

    result = await agent.run(
        title="Synthesize",
        description="",
        input_data={"research_results": [research_output]},
        context={},
    )
    assert isinstance(result, StrategyOutput)


# --- Persistence -----------------------------------------------------------


async def test_evidence_persists_and_is_traceable_to_task(session_factory):
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.services.evidence_service import EvidenceService
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("e@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        task = await TaskService(session).create_task(
            workspace_id=workspace.id, project_id=project.id, title="Research X", agent_type="research"
        )
        await session.commit()

        items = [
            EvidenceItem(claim="c1", source_url="https://example.com/1", query_used="q1"),
            EvidenceItem(claim="c2", source_url="https://example.com/2", query_used="q1"),
        ]
        await EvidenceService(session).store_many(
            workspace_id=workspace.id, project_id=project.id, task_id=task.id, items=items
        )
        await session.commit()
        project_id, task_id = project.id, task.id

    async with session_factory() as session:
        stored = await EvidenceService(session).list_for_project(project_id)
        assert len(stored) == 2
        assert all(e.task_id == task_id for e in stored)
        assert {e.source_url for e in stored} == {"https://example.com/1", "https://example.com/2"}
