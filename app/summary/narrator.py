"""Generate a 2-3 paragraph PT-BR narration from computed stats + schema.

Design:
- System prompt pins the persona (analista de dados PT-BR, tom neutro).
- User prompt packs schema + stats into a compact JSON blob — no raw data rows,
  avoiding both prompt-injection via cell values (PITFALLS.md#8) and leakage of
  the full dataset (PITFALLS.md#9).
- Response is Pydantic-parsed via `parse()` so we always get `{narration: str}`.
"""

from __future__ import annotations

import json

from app.core.config import get_settings
from app.llm.client import parse_structured
from app.schemas.summary import NarrationResponse
from app.summary.stats import SummaryStats

SYSTEM_PROMPT = (
    "Você é um analista de dados sênior. Produza uma narração breve em português "
    "do Brasil (2 a 3 parágrafos) sobre o dataset descrito. "
    "REGRAS DE FACTUALIDADE — siga TODAS:\n"
    "1. Use apenas os números fornecidos no JSON; não invente valores.\n"
    "2. Cardinalidade: chame de ALTA apenas se `unique` for próximo de `rows` "
    "(>50% das linhas). Cardinalidade BAIXA é `unique` ≤ 10. Não chame "
    "qualquer coluna categórica de \"alta cardinalidade\" sem checar.\n"
    "3. Alertas de qualidade só devem aparecer se houver evidência: "
    "`null_pct > 5%` para nulos, ou `unique` muito alto para alta cardinalidade.\n"
    "4. Se o dataset estiver limpo (sem nulos, baixa cardinalidade), diga isso "
    "explicitamente em vez de inventar problemas.\n"
    "5. Destaque: quantidade de linhas/colunas, ranges numéricos relevantes "
    "(mín-máx e média), e a categoria mais frequente em colunas textuais.\n"
    "6. NÃO use listas ou markdown; apenas parágrafos de prosa corrida."
)


def _build_user_prompt(stats: SummaryStats) -> str:
    payload: dict[str, object] = {
        "rows": stats.rows,
        "cols": stats.cols,
        "columns": [c.to_dict() for c in stats.columns],
    }
    return (
        "Resumo estatístico do dataset (JSON):\n\n"
        f"{json.dumps(payload, ensure_ascii=False, default=str)}"
    )


async def generate_narration(stats: SummaryStats, session_id: str | None = None) -> str:
    """Call the LLM to produce PT-BR narration. Raises on API failure."""
    settings = get_settings()
    response = await parse_structured(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(stats)},
        ],
        response_model=NarrationResponse,
        session_id=session_id,
        temperature=0.3,
        max_tokens=600,
    )
    return response.narration.strip()
