"""Narrate a single query result in 1-3 PT-BR sentences."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.llm.client import parse_structured
from app.schemas.nlq import NarrationOut, TableOut

if TYPE_CHECKING:
    from app.sessions.store import ConversationTurn

SYSTEM = (
    "Você é um analista de dados brasileiro. Dado o texto da pergunta do "
    "usuário, a SQL gerada e o resultado (primeiras linhas), escreva uma "
    "resposta de 1 a 3 frases em português do Brasil. "
    "Seja direto e factual — cite números do resultado quando relevantes. "
    "NÃO inclua SQL, código ou markdown na resposta; apenas prosa curta."
)


async def narrate_result(
    question: str,
    sql: str,
    table: TableOut,
    session_id: str | None = None,
    history: "list[ConversationTurn] | None" = None,
) -> str:
    settings = get_settings()
    # Cap the table sent to the LLM: at most 20 rows is enough context for
    # narration and keeps the prompt bounded.
    truncated_rows = table.rows[:20]
    payload: dict[str, object] = {
        "pergunta": question,
        "sql": sql,
        "resultado": {"columns": table.columns, "rows": truncated_rows},
    }
    if history:
        payload["historico"] = [
            {"pergunta": t.question, "resposta": t.text} for t in history
        ]
    out = await parse_structured(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)},
        ],
        response_model=NarrationOut,
        session_id=session_id,
        temperature=0.3,
        max_tokens=300,
    )
    return out.text.strip()
