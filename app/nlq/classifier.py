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
    "Você é um classificador permissivo. Dado o schema de um dataset tabular, "
    "o histórico recente da conversa, e uma nova pergunta em português, "
    "decida se a pergunta pode ser respondida com SQL sobre a tabela `dados`. "
    "\n\n"
    "Marque on_topic=True (sobre os dados) para QUALQUER uma destas situações:\n"
    "- Pergunta sobre uma ou mais colunas específicas do schema.\n"
    "- Meta-pergunta sobre o dataset inteiro: total de linhas, contagens, "
    "quantidade, distribuição, sumário, quais são as colunas.\n"
    "- Estatísticas (média, soma, máx, mín, mediana, distinto).\n"
    "- Filtros, ordenação, agrupamento, top-N.\n"
    "- Follow-ups baseados em perguntas anteriores ('e por região?', "
    "'qual o maior?', 'mostre os 10 primeiros').\n"
    "\n"
    "Marque on_topic=False APENAS para:\n"
    "- Conhecimento geral externo ('qual a capital do Brasil?').\n"
    "- Piadas, conversas casuais, opiniões.\n"
    "- Pedidos para escrever código não-SQL ou explicar conceitos abstratos.\n"
    "- Tópicos claramente sem ligação com análise de dados tabulares.\n"
    "\n"
    "Em caso de dúvida, prefira on_topic=True — perguntas vagas ainda podem "
    "virar SQL útil. Quem decide se vira SELECT bom é o gerador na próxima etapa."
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
