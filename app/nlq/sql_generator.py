"""LLM text-to-SQL with schema manifest + sample rows injected into the prompt.

Per NLQ-03, the prompt NEVER includes the full dataset — only aliases, dtypes,
and 3-5 sample values per column. This bounds both prompt cost and PII leakage.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.ingestion.service import SchemaManifest
from app.llm.client import parse_structured
from app.schemas.nlq import SQLResponse

if TYPE_CHECKING:
    from app.sessions.store import ConversationTurn

SYSTEM = (
    "Você é um gerador de SQL DuckDB. Dado o schema de uma tabela chamada "
    "`dados`, o histórico recente da conversa, e uma nova pergunta em "
    "português, gere EXATAMENTE UMA query SELECT DuckDB válida que "
    "responda a pergunta atual. "
    "Se a pergunta for follow-up (ex: 'e por região?', 'qual o maior?'), "
    "use o contexto do histórico para inferir o que o usuário quer. "
    "Regras obrigatórias:\n"
    "1. Use apenas a tabela `dados`. NUNCA use read_csv, read_parquet, ATTACH, "
    "INSTALL, LOAD, PRAGMA, COPY — essas funções estão bloqueadas.\n"
    "2. Use apenas os aliases ASCII das colunas (coluna `alias` do schema); "
    "NUNCA os nomes originais com acentos.\n"
    "3. Sempre termine com LIMIT 1000 quando o resultado puder ser grande.\n"
    "4. Responda em JSON no formato do response_format — sql com a query e "
    "reasoning com 1-2 frases em português."
)


def _build_schema_block(schema: SchemaManifest) -> str:
    cols = [
        {
            "alias": c.alias,
            "label": c.original_name,
            "dtype": c.dtype,
            "samples": c.sample_values[:5],
        }
        for c in schema.columns
    ]
    return json.dumps(
        {"table": "dados", "rows": schema.row_count, "columns": cols},
        ensure_ascii=False,
        default=str,
    )


def _history_block(history: "list[ConversationTurn] | None") -> str:
    """Compact serialization of prior turns — each turn shows the question,
    the SQL that answered it, and a one-liner describing the outcome."""
    if not history:
        return "(sem histórico)"
    lines: list[str] = []
    for i, t in enumerate(history):
        lines.append(
            f"Turno {i+1}:\n"
            f"  Pergunta: {t.question}\n"
            f"  SQL: {t.sql}\n"
            f"  Resposta resumida: {t.text}"
        )
    return "\n".join(lines)


async def generate_sql(
    question: str,
    schema: SchemaManifest,
    *,
    retry_reason: str | None = None,
    previous_sql: str | None = None,
    session_id: str | None = None,
    history: "list[ConversationTurn] | None" = None,
) -> SQLResponse:
    """Generate one DuckDB SELECT. `retry_reason` + `previous_sql` reinject the
    validator's complaint so the model can correct itself on retry.
    `history` is injected so follow-up questions can reuse prior context."""
    settings = get_settings()
    user_msg = (
        f"Schema:\n{_build_schema_block(schema)}\n\n"
        f"Histórico recente:\n{_history_block(history)}\n\n"
        f"Nova pergunta: {question}"
    )
    if retry_reason:
        user_msg += (
            f"\n\nTentativa anterior foi rejeitada. SQL anterior: {previous_sql!r}. "
            f"Motivo da rejeição: {retry_reason}. Corrija e gere uma nova SELECT."
        )

    return await parse_structured(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        response_model=SQLResponse,
        session_id=session_id,
        temperature=0.1,
        max_tokens=500,
    )
