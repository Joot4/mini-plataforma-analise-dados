"""Per-model token pricing table (USD per 1M tokens).

Source: OpenAI public pricing (2025-10 snapshot). When a new model is introduced,
add a row here; unknown models fall back to zero cost (logged but not estimated).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    input_per_1m: float  # USD per 1M input tokens
    output_per_1m: float  # USD per 1M output tokens


_PRICING: dict[str, ModelPricing] = {
    "gpt-4o-mini": ModelPricing(input_per_1m=0.15, output_per_1m=0.60),
    "gpt-4o": ModelPricing(input_per_1m=2.50, output_per_1m=10.00),
    "gpt-4.1-mini": ModelPricing(input_per_1m=0.40, output_per_1m=1.60),
    "gpt-4.1": ModelPricing(input_per_1m=2.00, output_per_1m=8.00),
    "gpt-4.1-nano": ModelPricing(input_per_1m=0.10, output_per_1m=0.40),
}


def estimate_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    """Estimate USD cost for a single call; returns 0.0 for unknown models."""
    pricing = _PRICING.get(model)
    if pricing is None:
        return 0.0
    return round(
        (tokens_in / 1_000_000) * pricing.input_per_1m
        + (tokens_out / 1_000_000) * pricing.output_per_1m,
        6,
    )
