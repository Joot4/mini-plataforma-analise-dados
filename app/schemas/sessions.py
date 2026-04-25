from __future__ import annotations

from pydantic import BaseModel

from app.schemas.upload import ColumnSchemaOut, SchemaManifestOut  # noqa: F401 re-export


class ConversationTurnOut(BaseModel):
    question: str
    text: str
    sql: str
    row_count: int
    truncated: bool
    asked_at: str


class SessionOut(BaseModel):
    session_id: str
    table_name: str
    created_at: str
    last_accessed_at: str
    schema_manifest: SchemaManifestOut
    history: list[ConversationTurnOut] = []


__all__ = [
    "SessionOut",
    "SchemaManifestOut",
    "ColumnSchemaOut",
    "ConversationTurnOut",
]
