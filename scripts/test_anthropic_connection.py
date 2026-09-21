"""Standalone connectivity check for the Anthropic provider.

Makes exactly ONE minimal real request to the Anthropic API to confirm that
MODEL_PROVIDER=anthropic is configured correctly end-to-end (key present and
valid, workspace header present if needed, AnthropicProvider wired up,
structured-output parsing works). It does NOT run the Jarvis orchestration
pipeline (planner/research/strategy/QA/execution) — it talks to
AnthropicProvider directly.

The API key and, if configured, ANTHROPIC_WORKSPACE_ID are never printed or
logged — only their presence is checked.

Usage:
    python scripts/test_anthropic_connection.py

Exit code 0 = the real Anthropic API request succeeded.
Exit code 1 = misconfiguration or a failed API request (reason printed, key/workspace id never printed).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app.agents.providers import AnthropicProvider, ModelProviderError  # noqa: E402
from app.config.settings import get_settings  # noqa: E402

SYSTEM_PROMPT = (
    "You are responding to an automated connectivity check. "
    "Return only the requested structured field."
)
USER_PROMPT = '{"instruction": "Confirm the connection by setting ok to true."}'


class ConnectivityCheck(BaseModel):
    ok: bool


def _error_message(exc: anthropic.APIStatusError) -> str:
    """Pulls the human-readable message out of an Anthropic error body, if
    present — this is Anthropic's own error text, never anything secret."""
    if isinstance(exc.body, dict):
        body_error = exc.body.get("error")
        if isinstance(body_error, dict):
            message = body_error.get("message")
            if message:
                return str(message)
    return str(exc)


def _classify_bad_request(message: str) -> str:
    """Categorizes a HTTP 400 Anthropic error message so the caller can print
    an actionable, specific failure reason. Pure/offline — unit-tested
    directly in tests/test_anthropic_workspace.py without needing to mock
    the SDK's async client."""
    lowered = message.lower()
    if "workspace" in lowered and ("scoped" in lowered or "workspace-id" in lowered):
        return "workspace_required"
    if "credit balance" in lowered or ("insufficient" in lowered and "credit" in lowered):
        return "insufficient_credits"
    if "model" in lowered:
        return "invalid_model"
    return "other"


async def main() -> int:
    settings = get_settings()

    if settings.model_provider.strip().lower() != "anthropic":
        print(
            "FAILURE: MODEL_PROVIDER is "
            f"'{settings.model_provider}', not 'anthropic'. Set MODEL_PROVIDER=anthropic in .env."
        )
        return 1

    if not settings.anthropic_api_key:
        print("FAILURE: ANTHROPIC_API_KEY is not set. (Key value is never printed.)")
        return 1

    print("MODEL_PROVIDER: anthropic")
    print("ANTHROPIC_API_KEY: configured (value withheld)")
    print(
        "ANTHROPIC_WORKSPACE_ID: "
        + ("configured (value withheld)" if settings.anthropic_workspace_id else "not configured")
    )
    print(f"Model under test (JARVIS_MODEL): {settings.jarvis_model}")

    provider = AnthropicProvider(
        api_key=settings.anthropic_api_key, workspace_id=settings.anthropic_workspace_id
    )

    try:
        result = await provider.complete_structured(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=USER_PROMPT,
            output_schema=ConnectivityCheck,
            model=settings.jarvis_model,
        )
    except anthropic.AuthenticationError:
        print("FAILURE: Authentication failed — the Anthropic API key was rejected (HTTP 401).")
        print("  Check that ANTHROPIC_API_KEY is correct and active.")
        return 1
    except anthropic.BadRequestError as e:
        message = _error_message(e)
        category = _classify_bad_request(message)
        if category == "workspace_required":
            print("FAILURE: This API key is not scoped to a workspace (HTTP 400).")
            print("  Set ANTHROPIC_WORKSPACE_ID in .env to the workspace this key belongs to.")
        elif category == "insufficient_credits":
            print("FAILURE: Insufficient Anthropic credits/billing issue (HTTP 400).")
            print("  Check your Anthropic account's billing/credit balance.")
        elif category == "invalid_model":
            print(
                "FAILURE: Anthropic rejected the request as invalid, likely the model id "
                f"(HTTP 400) — check that JARVIS_MODEL ('{settings.jarvis_model}') is a valid "
                "Anthropic model id."
            )
        else:
            print("FAILURE: Anthropic rejected the request as invalid (HTTP 400).")
        print(f"  Anthropic error message: {message}")
        return 1
    except anthropic.PermissionDeniedError as e:
        message = _error_message(e)
        if "credit" in message.lower() or "billing" in message.lower():
            print("FAILURE: Permission denied — likely an Anthropic billing/credit issue (HTTP 403).")
        else:
            print("FAILURE: Permission denied — the API key lacks access to this resource (HTTP 403).")
        print(f"  Anthropic error message: {message}")
        return 1
    except anthropic.NotFoundError:
        print(
            "FAILURE: Model or endpoint not found (HTTP 404) — check that JARVIS_MODEL "
            f"('{settings.jarvis_model}') is a valid Anthropic model id."
        )
        return 1
    except anthropic.RateLimitError:
        print("FAILURE: Rate limited by the Anthropic API (HTTP 429). Try again later.")
        return 1
    except anthropic.APIStatusError as e:
        message = _error_message(e)
        error_type = e.type or "unknown"
        request_id = e.request_id or "not provided"
        print(f"FAILURE: Anthropic API returned an error (status {e.status_code}).")
        print(f"  Anthropic error type: {error_type}")
        print(f"  Anthropic error message: {message}")
        print(f"  Request ID: {request_id}")
        return 1
    except anthropic.APIConnectionError:
        print("FAILURE: Could not connect to the Anthropic API (network error).")
        return 1
    except ModelProviderError as e:
        print(f"FAILURE: {e}")
        return 1

    if not isinstance(result, ConnectivityCheck) or not result.ok:
        print("FAILURE: Received a response, but it was not a valid/ok structured result.")
        return 1

    print("SUCCESS: Real Anthropic API request completed and returned a valid structured response.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
