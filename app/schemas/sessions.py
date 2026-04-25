from __future__ import annotations

from app.schemas.upload import ColumnSchemaOut, SchemaManifestOut  # noqa: F401 re-export
from pydantic import BaseModel


class SessionOut(BaseModel):
    session_id: str
    table_name: str
    created_at: str
    last_accessed_at: str
    schema_manifest: SchemaManifestOut


__all__ = ["SessionOut", "SchemaManifestOut", "ColumnSchemaOut"]
