from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UploadAcceptedResponse(BaseModel):
    """202 from POST /upload."""

    task_id: str
    status: str = "pending"
    message: str = "Upload aceito; processando em background."


class ColumnSchemaOut(BaseModel):
    alias: str
    original_name: str
    dtype: str
    sample_values: list[str | None] = Field(default_factory=list)


class SchemaManifestOut(BaseModel):
    columns: list[ColumnSchemaOut]
    row_count: int
    column_count: int
    original_columns: dict[str, str]


class CleaningReportOut(BaseModel):
    nulos_preenchidos: int
    duplicatas_removidas: int
    tipos_convertidos: list[str]
    colunas_pt_br_normalizadas: list[str]
    textos_padronizados: list[str]
    linhas_vazias_removidas: int
    colunas_vazias_removidas: list[str]


class LoadMetadataOut(BaseModel):
    format: str
    encoding: str | None = None
    delimiter: str | None = None
    sheets_ignored: list[str] = Field(default_factory=list)


class IngestResultOut(BaseModel):
    schema_manifest: SchemaManifestOut = Field(..., alias="schema")
    cleaning_report: CleaningReportOut
    load: LoadMetadataOut

    model_config = {"populate_by_name": True}


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: float
    created_at: str
    updated_at: str
    result: dict[str, Any] | None = None
    error: dict[str, str] | None = None
