"""End-to-end orchestrator tests with monkeypatched LLM calls and a real
DuckDB session. Validates classify → gen → validate → exec → narrate → chart
+ the retry path + the error envelopes for off-topic / invalid-question.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.ingestion.service import ColumnSchema, SchemaManifest
from app.nlq import service as nlq_service
from app.nlq.service import NLQError, answer_question
from app.schemas.nlq import ClassifyResponse, SQLResponse
from app.sessions.store import SESSION_TABLE_NAME, SessionStore


def _manifest(df: pd.DataFrame, types: dict[str, str] | None = None) -> SchemaManifest:
    types = types or {c: str(df[c].dtype) for c in df.columns}
    cols = [
        ColumnSchema(alias=c, original_name=c, dtype=types[c], sample_values=[]) for c in df.columns
    ]
    return SchemaManifest(
        columns=cols,
        row_count=len(df),
        column_count=len(df.columns),
        original_columns={c: c for c in df.columns},
    )


@pytest.fixture
def session():
    df = pd.DataFrame(
        {
            "regiao": ["Sul", "Norte", "Sul", "Sudeste", "Sul"],
            "vendas": [100.0, 200.0, 150.0, 500.0, 80.0],
        }
    )
    store = SessionStore(ttl_seconds=3600)
    rec = store.create(
        user_id="u1", df=df, schema=_manifest(df, {"regiao": "string", "vendas": "float64"})
    )
    yield rec
    rec.close()


def _patch_llm(
    monkeypatch, *, on_topic: bool, sql: str, narration: str, retry_sql: str | None = None
):
    """Monkeypatch classifier / sql-generator / narrator with canned responses."""
    calls = {"generate_sql": 0}

    async def fake_classify(question, schema, session_id=None, history=None):
        return ClassifyResponse(on_topic=on_topic, reason="ok")

    async def fake_generate(
        question,
        schema,
        *,
        retry_reason=None,
        previous_sql=None,
        session_id=None,
        history=None,
    ):
        calls["generate_sql"] += 1
        if calls["generate_sql"] == 1:
            return SQLResponse(sql=sql, reasoning="primeira tentativa")
        return SQLResponse(sql=retry_sql or sql, reasoning="segunda tentativa")

    async def fake_narrate(question, sql, table, session_id=None, history=None):
        return narration

    monkeypatch.setattr(nlq_service, "classify_question", fake_classify)
    monkeypatch.setattr(nlq_service, "generate_sql", fake_generate)
    monkeypatch.setattr(nlq_service, "narrate_result", fake_narrate)
    return calls


@pytest.mark.asyncio
async def test_happy_path_returns_full_response(session, monkeypatch) -> None:
    _patch_llm(
        monkeypatch,
        on_topic=True,
        sql=f"SELECT regiao, SUM(vendas) AS total FROM {SESSION_TABLE_NAME} GROUP BY regiao",
        narration="O Sul teve 330 em vendas e o Sudeste 500.",
    )
    out = await answer_question(session, "Qual o total por região?")
    assert out.text
    assert out.generated_sql.upper().startswith("SELECT")
    assert out.table.columns == ["regiao", "total"]
    assert len(out.table.rows) == 3  # 3 distinct regions
    assert out.table.truncated is False
    # categorical + numeric → bar
    assert out.chart_spec is not None
    assert out.chart_spec["mark"] == "bar"


@pytest.mark.asyncio
async def test_off_topic_raises_out_of_scope(session, monkeypatch) -> None:
    _patch_llm(monkeypatch, on_topic=False, sql="", narration="")
    with pytest.raises(NLQError) as exc_info:
        await answer_question(session, "Qual a capital do Brasil?")
    assert exc_info.value.error_type == "out_of_scope"


@pytest.mark.asyncio
async def test_invalid_sql_retries_once_then_fails(session, monkeypatch) -> None:
    calls = _patch_llm(
        monkeypatch,
        on_topic=True,
        sql="DROP TABLE dados",  # invalid
        narration="",
        retry_sql="DELETE FROM dados",  # still invalid
    )
    with pytest.raises(NLQError) as exc_info:
        await answer_question(session, "apagar tudo")
    assert exc_info.value.error_type == "invalid_question"
    # Exactly 2 attempts (first + 1 retry).
    assert calls["generate_sql"] == 2


@pytest.mark.asyncio
async def test_invalid_first_attempt_retry_succeeds(session, monkeypatch) -> None:
    _patch_llm(
        monkeypatch,
        on_topic=True,
        sql="DROP TABLE dados",  # first attempt — invalid
        retry_sql=f"SELECT regiao FROM {SESSION_TABLE_NAME} LIMIT 5",
        narration="Retornei 5 regiões.",
    )
    out = await answer_question(session, "lista de regiões")
    assert out.generated_sql.upper().startswith("SELECT")


@pytest.mark.asyncio
async def test_truncation_at_1000_rows(monkeypatch) -> None:
    df = pd.DataFrame({"n": list(range(1500)), "v": [float(i) for i in range(1500)]})
    store = SessionStore(ttl_seconds=3600)
    rec = store.create(user_id="u", df=df, schema=_manifest(df, {"n": "int64", "v": "float64"}))
    try:
        _patch_llm(
            monkeypatch,
            on_topic=True,
            sql=f"SELECT n, v FROM {SESSION_TABLE_NAME}",
            narration="Lista completa.",
        )
        out = await answer_question(rec, "me dê tudo")
        assert out.table.truncated is True
        assert len(out.table.rows) == 1000
    finally:
        rec.close()


@pytest.mark.asyncio
async def test_chart_spec_is_none_for_single_column_result(session, monkeypatch) -> None:
    _patch_llm(
        monkeypatch,
        on_topic=True,
        sql=f"SELECT DISTINCT regiao FROM {SESSION_TABLE_NAME}",
        narration="3 regiões distintas.",
    )
    out = await answer_question(session, "quais regiões?")
    assert out.chart_spec is None
    assert len(out.table.columns) == 1
