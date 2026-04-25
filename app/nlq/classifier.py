"""Classify whether a user question can be answered with the session's dataset.

Keeps a short PT-BR prompt — the system message pins the persona (analista
brasileiro) and the user message includes only schema aliases + dtypes (not
sample rows, to keep the classifier cheap and fast).
"""
from __future__ import annotations

import json

from app.core.config import get_settings
from app.ingestion.service import SchemaManifest
from app.llm.client import parse_structured
from app.schemas.nlq import ClassifyResponse

SYSTEM = (
    "Você é um classificador. Dado o schema de um dataset tabular e uma "
    "pergunta em português, decida se a pergunta pode ser respondida com "
    "as colunas disponíveis. "
    "Retorne on_topic=True se a pergunta for sobre os dados; "
    "on_topic=False para perguntas gerais, piadas, conhecimento externo, "
    "ou assuntos sem relação com as colunas."
)


def _schema_summary(schema: SchemaManifest) -> str:
    cols = [
        {"alias": c.alias, "label": c.original_name, "dtype": c.dtype}
        for c in schema.columns
    ]
    return json.dumps(
        {"rows": schema.row_count, "columns": cols},
        ensure_ascii=False,
        default=str,
    )


async def classify_question(
    question: str, schema: SchemaManifest, session_id: str | None = None
) -> ClassifyResponse:
    settings = get_settings()
    return await parse_structured(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Schema:\n{_schema_summary(schema)}\n\nPergunta: {question}"
                ),
            },
        ],
        response_model=ClassifyResponse,
        session_id=session_id,
        temperature=0.0,
        max_tokens=150,
    )
