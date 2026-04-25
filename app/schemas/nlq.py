from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# --- LLM structured-output schemas (sent to OpenAI as response_format) ---


class ClassifyResponse(BaseModel):
    """LLM classifier output — is the user's question on-topic for this dataset?"""

    on_topic: bool = Field(
        ...,
        description=(
            "True se a pergunta pode ser respondida com a tabela dados desta "
            "sessão; False se for off-topic (piada, pergunta geral, etc.)."
        ),
    )
    reason: str = Field(
        ...,
        description="Breve justificativa em português (1-2 frases).",
    )


class SQLResponse(BaseModel):
    """LLM SQL generator output."""

    sql: str = Field(..., description="SQL DuckDB SELECT válido.")
    reasoning: str = Field(
        ..., description="Raciocínio de 1-2 frases em português explicando a query."
    )


class NarrationOut(BaseModel):
    """LLM narrator output for a single query result."""

    text: str = Field(..., description="Explicação em PT-BR com 1-3 frases.")


# --- Public API schemas ---


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)


class TableOut(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool = False


class QueryResponse(BaseModel):
    text: str
    table: TableOut
    chart_spec: dict[str, Any] | None = None
    generated_sql: str
    reasoning: str | None = None


__all__ = [
    "ClassifyResponse",
    "SQLResponse",
    "NarrationOut",
    "QueryRequest",
    "TableOut",
    "QueryResponse",
]
