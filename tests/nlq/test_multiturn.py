"""Multi-turn / conversational memory tests.

Verifies:
- A successful answer appends a ConversationTurn to the session.
- The second question receives the first turn as `history=` in classifier,
  sql_generator, and narrator — so follow-ups like "e por região?" can work.
- GET /sessions/{id} returns the history.
- DELETE /sessions/{id}/conversation clears it.
"""

from __future__ import annotations

import os
import secrets

import pandas as pd
import pytest
from httpx import AsyncClient

from app.ingestion.service import ColumnSchema, SchemaManifest
from app.nlq import service as nlq_service
from app.nlq.service import answer_question
from app.schemas.nlq import ClassifyResponse, SQLResponse
from app.sessions.store import SESSION_TABLE_NAME, SessionStore
from tests.fixtures.ptbr_data import ptbr_csv_utf8_comma

API = "/api/v1"
_PW = os.environ.get("PYTEST_USER_PW") or secrets.token_urlsafe(16)
_FAKE_KEY = "sk-" + secrets.token_hex(16)


def _manifest(df, types=None):
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
            "regiao": ["Sul", "Norte", "Sul", "Sudeste"],
            "vendas": [100.0, 200.0, 150.0, 500.0],
        }
    )
    store = SessionStore(ttl_seconds=3600)
    rec = store.create(
        user_id="u1",
        df=df,
        schema=_manifest(df, {"regiao": "string", "vendas": "float64"}),
    )
    yield rec
    rec.close()


@pytest.mark.asyncio
async def test_successful_turn_is_appended_to_history(session, monkeypatch) -> None:
    async def fake_classify(q, s, session_id=None, history=None):
        return ClassifyResponse(on_topic=True, reason="ok")

    async def fake_gen(
        q, s, *, retry_reason=None, previous_sql=None, session_id=None, history=None
    ):
        return SQLResponse(
            sql=f"SELECT SUM(vendas) AS total FROM {SESSION_TABLE_NAME}", reasoning="-"
        )

    async def fake_narrate(q, sql, table, session_id=None, history=None):
        return "O total é 950."

    monkeypatch.setattr(nlq_service, "classify_question", fake_classify)
    monkeypatch.setattr(nlq_service, "generate_sql", fake_gen)
    monkeypatch.setattr(nlq_service, "narrate_result", fake_narrate)

    assert session.history == []
    await answer_question(session, "qual o total?")
    assert len(session.history) == 1
    turn = session.history[0]
    assert turn.question == "qual o total?"
    assert turn.text == "O total é 950."
    assert "SUM(vendas)" in turn.sql


@pytest.mark.asyncio
async def test_second_turn_receives_history_in_prompts(session, monkeypatch) -> None:
    """Ask two questions; assert the 2nd call to each LLM helper receives the
    1st turn in its `history` kwarg."""
    captured = {"classify": [], "generate": [], "narrate": []}

    async def fake_classify(q, s, session_id=None, history=None):
        captured["classify"].append(list(history or []))
        return ClassifyResponse(on_topic=True, reason="ok")

    async def fake_gen(
        q, s, *, retry_reason=None, previous_sql=None, session_id=None, history=None
    ):
        captured["generate"].append(list(history or []))
        return SQLResponse(
            sql=f"SELECT regiao, SUM(vendas) AS total FROM {SESSION_TABLE_NAME} GROUP BY regiao",
            reasoning="-",
        )

    async def fake_narrate(q, sql, table, session_id=None, history=None):
        captured["narrate"].append(list(history or []))
        return "pronto."

    monkeypatch.setattr(nlq_service, "classify_question", fake_classify)
    monkeypatch.setattr(nlq_service, "generate_sql", fake_gen)
    monkeypatch.setattr(nlq_service, "narrate_result", fake_narrate)

    await answer_question(session, "total de vendas?")
    await answer_question(session, "e por região?")

    # First turn sees empty history, second sees 1 prior turn.
    assert captured["classify"][0] == []
    assert captured["generate"][0] == []
    assert captured["narrate"][0] == []
    assert len(captured["classify"][1]) == 1
    assert captured["classify"][1][0].question == "total de vendas?"
    assert len(captured["generate"][1]) == 1
    assert len(captured["narrate"][1]) == 1


@pytest.mark.asyncio
async def test_history_capped_at_max_turns(session, monkeypatch) -> None:
    """The LLM prompt should only see the last N turns (MAX_HISTORY_TURNS = 3)
    even after more questions."""
    from app.sessions.store import MAX_HISTORY_TURNS

    captured = []

    async def fake_classify(q, s, session_id=None, history=None):
        captured.append(len(history or []))
        return ClassifyResponse(on_topic=True, reason="ok")

    async def fake_gen(
        q, s, *, retry_reason=None, previous_sql=None, session_id=None, history=None
    ):
        return SQLResponse(sql=f"SELECT COUNT(*) FROM {SESSION_TABLE_NAME}", reasoning="-")

    async def fake_narrate(q, sql, table, session_id=None, history=None):
        return "ok."

    monkeypatch.setattr(nlq_service, "classify_question", fake_classify)
    monkeypatch.setattr(nlq_service, "generate_sql", fake_gen)
    monkeypatch.setattr(nlq_service, "narrate_result", fake_narrate)

    for i in range(MAX_HISTORY_TURNS + 3):
        await answer_question(session, f"pergunta {i}")

    assert captured[0] == 0
    assert captured[-1] == MAX_HISTORY_TURNS  # cap holds


# --- API-level tests ---


async def _login(client, email):
    await client.post(f"{API}/auth/register", json={"email": email, "password": _PW})
    r = await client.post(f"{API}/auth/login", json={"email": email, "password": _PW})
    return r.json()["access_token"]


async def _session_id(client, token):
    import asyncio

    r = await client.post(
        f"{API}/upload",
        files={"file": ("u.csv", ptbr_csv_utf8_comma(), "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    task_id = r.json()["task_id"]
    for _ in range(200):
        s = await client.get(
            f"{API}/upload/{task_id}/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        if s.json()["status"] == "done":
            return s.json()["result"]["session_id"]
        await asyncio.sleep(0.05)
    raise AssertionError("upload did not finish")


@pytest.mark.asyncio
async def test_get_session_returns_history(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", _FAKE_KEY)

    async def fc(q, s, session_id=None, history=None):
        return ClassifyResponse(on_topic=True, reason="ok")

    async def fg(q, s, *, retry_reason=None, previous_sql=None, session_id=None, history=None):
        return SQLResponse(sql="SELECT COUNT(*) FROM dados", reasoning="-")

    async def fn(q, sql, table, session_id=None, history=None):
        return f"resposta para: {q}"

    monkeypatch.setattr("app.nlq.service.classify_question", fc)
    monkeypatch.setattr("app.nlq.service.generate_sql", fg)
    monkeypatch.setattr("app.nlq.service.narrate_result", fn)

    token = await _login(client, "mtq@example.com")
    sid = await _session_id(client, token)

    # Ask 2 questions
    for q in ["quantas linhas?", "e colunas?"]:
        r = await client.post(
            f"{API}/sessions/{sid}/query",
            json={"question": q},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200

    # Verify GET /sessions/{id} returns history
    r = await client.get(f"{API}/sessions/{sid}", headers={"Authorization": f"Bearer {token}"})
    body = r.json()
    assert len(body["history"]) == 2
    assert body["history"][0]["question"] == "quantas linhas?"
    assert body["history"][1]["question"] == "e colunas?"

    # DELETE conversation clears it
    r = await client.delete(
        f"{API}/sessions/{sid}/conversation",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204

    r = await client.get(f"{API}/sessions/{sid}", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["history"] == []
