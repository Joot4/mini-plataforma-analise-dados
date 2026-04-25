"""End-to-end NL query orchestration for a single session.

Flow:
1. Classify on-topic (LLM call 1, structured).
2. Generate SQL (LLM call 2, structured).
3. Validate SQL (sqlglot AST — two layers from Phase 3).
4. If invalid → retry once with error injected into the prompt.
5. Execute SQL on the session's hardened DuckDB conn.
6. Truncate result to 1000 rows (NLQ-06).
7. Narrate result (LLM call 3).
8. Build deterministic chart spec.

All LLM calls flow through `parse_structured` so OPS-03 logs happen automatically.
DuckDB execution runs in a worker thread (SQL-05 — never block the event loop).
"""

from __future__ import annotations

import asyncio
import math
from typing import Any

import pandas as pd

from app.core.logging import get_logger
from app.duckdb_.validator import SQLValidationError, validate_sql_or_raise
from app.nlq.chart import build_chart_spec
from app.nlq.classifier import classify_question
from app.nlq.narrator import narrate_result
from app.nlq.sql_generator import generate_sql
from app.schemas.nlq import QueryResponse, TableOut
from app.sessions.store import ConversationTurn, SessionRecord

logger = get_logger("app.nlq")

MAX_ROWS = 1000


class NLQError(Exception):
    """Domain error from the NL query pipeline."""

    def __init__(self, error_type: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.status_code = status_code


def _run_sql_sync(conn, sql: str) -> pd.DataFrame:
    return conn.execute(sql).fetch_df()


def _df_to_table(df: pd.DataFrame) -> TableOut:
    truncated = False
    if len(df) > MAX_ROWS:
        df = df.head(MAX_ROWS)
        truncated = True
    # Normalize for JSON: NaN → None, datetimes → ISO.
    cleaned = df.copy()
    for col in cleaned.columns:
        s = cleaned[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            cleaned[col] = s.dt.strftime("%Y-%m-%dT%H:%M:%S").where(s.notna(), None)
        elif pd.api.types.is_float_dtype(s):
            cleaned[col] = (
                s.where(s.notna(), None)
                .astype(object)
                .map(lambda v: None if (isinstance(v, float) and math.isnan(v)) else v)
            )
    rows: list[list[Any]] = cleaned.astype(object).where(cleaned.notna(), None).values.tolist()
    return TableOut(columns=list(cleaned.columns), rows=rows, truncated=truncated)


async def answer_question(session: SessionRecord, question: str) -> QueryResponse:
    """Run the full NL query pipeline against a session."""
    recent = session.recent_turns()

    # 1. Classify on-topic (with conversational context).
    classification = await classify_question(
        question,
        session.schema,
        session_id=session.session_id,
        history=recent,
    )
    if not classification.on_topic:
        raise NLQError(
            error_type="out_of_scope",
            message=(
                "Esta pergunta não parece se relacionar com os dados da sessão. "
                f"{classification.reason}"
            ),
        )

    # 2. Generate SQL (with 1 retry if validator rejects).
    attempt = await generate_sql(
        question,
        session.schema,
        session_id=session.session_id,
        history=recent,
    )
    sql = attempt.sql
    try:
        validate_sql_or_raise(sql)
    except SQLValidationError as first_err:
        logger.info(
            "nlq.sql_retry",
            session_id=session.session_id,
            reason=first_err.reason,
            layer=first_err.layer,
        )
        attempt = await generate_sql(
            question,
            session.schema,
            retry_reason=first_err.reason,
            previous_sql=sql,
            session_id=session.session_id,
            history=recent,
        )
        sql = attempt.sql
        try:
            validate_sql_or_raise(sql)
        except SQLValidationError as second_err:
            raise NLQError(
                error_type="invalid_question",
                message=(
                    "Não consegui gerar uma consulta válida para essa pergunta. "
                    "Tente reformular com termos mais próximos das colunas disponíveis."
                ),
            ) from second_err

    # 3. Execute on the session's hardened DuckDB conn (off-loop).
    try:
        df = await asyncio.to_thread(_run_sql_sync, session.connection, sql)
    except Exception as exc:
        logger.warning("nlq.execution_failed", session_id=session.session_id, exc_info=exc)
        raise NLQError(
            error_type="execution_failed",
            message=f"A consulta foi gerada mas falhou ao executar: {exc}",
        ) from exc

    # 4. Format table + truncation flag.
    table = _df_to_table(df)

    # 5. Narrate (best-effort; if narration fails we still return the data).
    try:
        text = await narrate_result(
            question,
            sql,
            table,
            session_id=session.session_id,
            history=recent,
        )
    except Exception as exc:
        logger.warning("nlq.narration_failed", session_id=session.session_id, exc_info=exc)
        text = (
            f"Retornei {len(table.rows)} linhas da consulta. "
            "A narração em linguagem natural falhou — verifique o resultado."
        )

    # 6. Chart spec (deterministic).
    try:
        chart_spec = build_chart_spec(df.head(MAX_ROWS))
    except Exception as exc:
        logger.warning("nlq.chart_failed", session_id=session.session_id, exc_info=exc)
        chart_spec = None

    # 7. Persist the turn so next follow-up has context.
    session.append_turn(
        ConversationTurn(
            question=question,
            text=text,
            sql=sql,
            row_count=len(table.rows),
            truncated=table.truncated,
        )
    )

    return QueryResponse(
        text=text,
        table=table,
        chart_spec=chart_spec,
        generated_sql=sql,
        reasoning=attempt.reasoning,
    )
