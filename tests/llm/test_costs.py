from __future__ import annotations

from app.llm.costs import estimate_cost_usd


def test_known_model_costs_calculated() -> None:
    # 1M in + 1M out on gpt-4o-mini = 0.15 + 0.60 = 0.75
    assert estimate_cost_usd("gpt-4o-mini", 1_000_000, 1_000_000) == 0.75


def test_partial_token_cost() -> None:
    # 1000 in on gpt-4o-mini = 0.15 / 1000 = 0.00015
    assert estimate_cost_usd("gpt-4o-mini", 1_000, 0) == 0.00015


def test_unknown_model_returns_zero() -> None:
    assert estimate_cost_usd("imaginary-model-v999", 10_000, 5_000) == 0.0
