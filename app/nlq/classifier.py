"""Classify whether a user question can be answered with the session's dataset.

Keeps a short PT-BR prompt — the system message pins the persona (analista
brasileiro) and the user message includes only schema aliases + dtypes (not
sample rows, to keep the classifier cheap and fast).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.ingestion.service import SchemaManifest
from app.llm.client import parse_structured
from app.schemas.nlq import ClassifyResponse

if TYPE_CHECKING:
    from app.sessions.store import ConversationTurn

SYSTEM = (
    "Você é um classificador. Dado o schema de um dataset tabular, o histórico "
    "recente da conversa, e uma nova pergunta em português, decida se a "
    "pergunta pode ser respondida com as colunas disponíveis. "
    "Perguntas de follow-up como 'e por região?' ou 'qual o maior?' devem "
    "ser interpretadas no contexto das perguntas anteriores. "
    "Retorne on_topic=True se a pergunta (com o contexto) for sobre os dados; "
    "on_topic=False para perguntas gerais, piadas, conhecimento externo, "
    "ou assuntos sem relação com as colunas."
)


def _schema_summary(schema: SchemaManifest) -> str:
    cols = [{"alias": c.alias, "label": c.original_name, "dtype": c.dtype} for c in schema.columns]
    return json.dumps(
        {"rows": schema.row_count, "columns": cols},
        ensure_ascii=False,
        default=str,
    )


def _history_block(history: list[ConversationTurn] | None) -> str:
    if not history:
        return "(sem histórico)"
    lines = [
        f"{i + 1}. Pergunta: {t.question}\n   Resposta: {t.text}" for i, t in enumerate(history)
    ]
    return "\n".join(lines)


async def classify_question(
    question: str,
    schema: SchemaManifest,
    session_id: str | None = None,
    history: list[ConversationTurn] | None = None,
) -> ClassifyResponse:
    settings = get_settings()
    user_content = (
        f"Schema:\n{_schema_summary(schema)}\n\n"
        f"Histórico recente:\n{_history_block(history)}\n\n"
        f"Nova pergunta: {question}"
    )
    return await parse_structured(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_content},
        ],
        response_model=ClassifyResponse,
        session_id=session_id,
        temperature=0.0,
        max_tokens=150,
    )
