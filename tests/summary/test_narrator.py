from __future__ import annotations

import pytest

from app.schemas.summary import NarrationResponse
from app.summary.narrator import SYSTEM_PROMPT, _build_user_prompt, generate_narration
from app.summary.stats import ColumnStats, SummaryStats


@pytest.fixture
def stats() -> SummaryStats:
    return SummaryStats(
        rows=123,
        cols=2,
        columns=[
            ColumnStats(
                alias="preco",
                label="Preço (R$)",
                dtype="float64",
                kind="numeric",
                null_pct=0.0,
                unique=100,
                min=10.0,
                max=1000.0,
                mean=450.5,
                median=400.0,
            ),
            ColumnStats(
                alias="regiao",
                label="Região",
                dtype="string",
                kind="categorical",
                null_pct=2.0,
                unique=5,
                top5=[{"value": "Sudeste", "freq": 60}, {"value": "Sul", "freq": 40}],
            ),
        ],
    )


def test_user_prompt_includes_stats(stats) -> None:
    prompt = _build_user_prompt(stats)
    assert "123" in prompt  # row count
    assert "preco" in prompt
    assert "Sudeste" in prompt
    # Must NOT contain raw cell values (we don't send any — only aggregates).
    assert "raw rows" not in prompt.lower()


@pytest.mark.asyncio
async def test_generate_narration_uses_structured_client(monkeypatch, stats) -> None:
    captured = {}

    async def fake_parse(**kwargs):
        captured.update(kwargs)
        return NarrationResponse(narration="O dataset tem 123 linhas em 2 colunas. " * 3)

    monkeypatch.setattr("app.summary.narrator.parse_structured", fake_parse)

    out = await generate_narration(stats, session_id="sess-xyz")
    assert "123 linhas" in out
    # Verify prompts were built from our content.
    assert captured["response_model"] is NarrationResponse
    assert captured["session_id"] == "sess-xyz"
    system_msg = captured["messages"][0]
    assert system_msg["role"] == "system"
    assert system_msg["content"] == SYSTEM_PROMPT
