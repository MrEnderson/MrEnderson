"""FastAPI endpoint tests against an isolated temp-file SQLite database."""
from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config.settings import get_settings
from app.database import connection as db_connection


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / f"api_test_{uuid.uuid4().hex}.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    # Force the MockProvider regardless of the developer's shell/.env — API tests
    # must never make real network calls, even if a real API key is configured.
    # Note: monkeypatch.delenv() alone is NOT enough here — pydantic-settings falls
    # back to reading .env for any key absent from the process environment, so an
    # OPENAI_API_KEY/ANTHROPIC_API_KEY left in .env would still be picked up.
    # Setting MODEL_PROVIDER=mock explicitly is what actually guarantees isolation.
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    # Same reasoning for the research side — see conftest.py's
    # _safe_research_provider_env, which already forces this for every test,
    # but /chat exercises the module-level `_registry`/`_provider` in
    # app.api.routes directly, so it's worth being explicit here too.
    monkeypatch.setenv("RESEARCH_PROVIDER", "dev")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    get_settings.cache_clear()
    asyncio.run(db_connection.reset_engine())

    from app.main import app

    with TestClient(app) as c:
        yield c

    asyncio.run(db_connection.reset_engine())
    get_settings.cache_clear()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body["agents"]) == {"jarvis", "research", "strategy", "execution", "qa"}


def test_create_workspace(client):
    response = client.post(
        "/workspaces", json={"user_email": "api@example.com", "name": "API Workspace"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "API Workspace"
    assert body["id"]


def test_create_workspace_invalid_payload_returns_422(client):
    response = client.post("/workspaces", json={"name": "Missing email"})
    assert response.status_code == 422


def test_get_missing_project_returns_404(client):
    response = client.get(f"/projects/{uuid.uuid4()}")
    assert response.status_code == 404


def test_chat_runs_full_objective_and_lists_tasks(client):
    response = client.post(
        "/chat",
        json={
            "user_email": "chat@example.com",
            "objective": "Find three potential digital-product opportunities and recommend the strongest one.",
        },
    )
    assert response.status_code == 200
    body = response.json()
    # MockProvider's research output always self-labels insufficient_evidence,
    # so its self-QA always ends at NEEDS_REVIEW after exhausting retries —
    # the mission status must honestly reflect that (COMPLETED_WITH_REVIEW),
    # not a plain COMPLETED. Every individual TASK still reaches the
    # COMPLETED task-state (none of them hard-failed).
    assert body["status"] == "COMPLETED_WITH_REVIEW"
    assert len(body["tasks"]) == 5
    assert all(t["status"] == "COMPLETED" for t in body["tasks"])

    tasks_response = client.get(f"/projects/{body['project_id']}/tasks")
    assert tasks_response.status_code == 200
    assert len(tasks_response.json()) == 5

    audit_response = client.get(f"/projects/{body['project_id']}/audit")
    assert audit_response.status_code == 200
    assert len(audit_response.json()) > 0


def test_chat_with_risky_objective_requires_approval(client):
    response = client.post(
        "/chat",
        json={
            "user_email": "risk@example.com",
            "objective": "Purchase advertising credits and publish the campaign immediately.",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "NEEDS_APPROVAL"
    assert body["approvals_required"]

    needs_approval_task = next(
        t for t in body["tasks"] if t["status"] == "NEEDS_APPROVAL"
    )
    approve_response = client.post(
        f"/tasks/{needs_approval_task['id']}/approve",
        json={"resolved_by": "owner@example.com", "decision_reason": "ok to proceed"},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "APPROVED"


def test_approve_task_without_approval_request_returns_404(client):
    response = client.post(
        f"/tasks/{uuid.uuid4()}/approve",
        json={"resolved_by": "owner@example.com"},
    )
    assert response.status_code == 404
