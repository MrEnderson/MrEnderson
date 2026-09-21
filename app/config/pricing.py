"""Configurable model pricing, kept strictly separate from USAGE.

Pricing is never hard-coded here — it comes only from `MODEL_PRICING_JSON`
(see app/config/settings.py). If a model has no configured entry,
`estimate_cost_usd` returns None rather than guessing, so callers can always
tell USAGE (always real, from the provider) apart from ESTIMATED_COST (only
present when pricing was explicitly configured for that exact model id).
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.config.settings import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ModelPricing:
    input_per_million_usd: float
    output_per_million_usd: float


def get_pricing_table() -> dict[str, ModelPricing]:
    settings = get_settings()
    raw = settings.model_pricing_json or "{}"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("model_pricing_json_invalid")
        return {}

    table: dict[str, ModelPricing] = {}
    for model, rates in parsed.items():
        try:
            table[model] = ModelPricing(
                input_per_million_usd=float(rates["input_per_million_usd"]),
                output_per_million_usd=float(rates["output_per_million_usd"]),
            )
        except (KeyError, TypeError, ValueError):
            logger.error("model_pricing_entry_invalid", model=model)
    return table


def estimate_cost_usd(
    *, model: str, input_tokens: int | None, output_tokens: int | None
) -> float | None:
    if input_tokens is None or output_tokens is None:
        return None
    pricing = get_pricing_table().get(model)
    if pricing is None:
        return None
    return (
        (input_tokens / 1_000_000) * pricing.input_per_million_usd
        + (output_tokens / 1_000_000) * pricing.output_per_million_usd
    )
