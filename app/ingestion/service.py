"""High-level ingestion orchestrator.

`ingest_file(path)` runs the full pipeline: load → normalize columns → clean →
produce schema manifest + cleaning report + metadata.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from app.ingestion.cleaning import CleaningOptions, CleaningReport, clean_dataframe
from app.ingestion.normalize import normalize_column_names
from app.ingestion.reader import LoadResult, load_file


@dataclass
class ColumnSchema:
    alias: str
    original_name: str
    dtype: str
    sample_values: list[str | None] = field(default_factory=list)


@dataclass
class SchemaManifest:
    columns: list[ColumnSchema]
    row_count: int
    column_count: int
    original_columns: dict[str, str]  # alias -> original
    # Preview of the first N rows for the UI. Kept separate from
    # `ColumnSchema.sample_values` so the LLM context stays small.
    preview: dict[str, object] = field(
        default_factory=lambda: {"columns": [], "rows": []}
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "columns": [asdict(c) for c in self.columns],
            "row_count": self.row_count,
            "column_count": self.column_count,
            "original_columns": self.original_columns,
            "preview": self.preview,
        }


PREVIEW_ROW_COUNT = 20


def _build_preview(
    df: pd.DataFrame, label_map: dict[str, str], n: int = PREVIEW_ROW_COUNT
) -> dict[str, object]:
    """First N rows of `df`, JSON-serializable, with original column labels."""
    sliced = df.head(n).copy()
    for col in sliced.columns:
        s = sliced[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            sliced[col] = s.dt.strftime("%Y-%m-%d %H:%M:%S").where(s.notna(), None)
    sliced = sliced.astype(object).where(sliced.notna(), None)
    return {
        "columns": [label_map[a] for a in sliced.columns],
        "rows": sliced.values.tolist(),
    }


@dataclass
class IngestResult:
    df: pd.DataFrame
    schema: SchemaManifest
    cleaning_report: CleaningReport
    load: LoadResult
    raw_row_count: int = 0  # row count BEFORE cleaning (for limit enforcement)

    def to_response(self) -> dict[str, object]:
        return {
            "schema": self.schema.to_dict(),
            "cleaning_report": self.cleaning_report.to_dict(),
            "load": {
                "format": self.load.format,
                "encoding": self.load.encoding,
                "delimiter": self.load.delimiter,
                "sheets_ignored": self.load.sheets_ignored,
            },
        }


def ingest_file(path: Path, options: CleaningOptions | None = None) -> IngestResult:
    """Run the full ingestion pipeline on a file on disk."""
    loaded = load_file(path)
    df = loaded.df
    raw_row_count = int(len(df))

    # Normalize column names (PT-BR → ASCII snake_case) + preserve mapping.
    aliases, mapping = normalize_column_names(list(df.columns))
    df = df.rename(columns=dict(zip(df.columns, aliases, strict=True)))

    # Clean the data.
    cleaned, report = clean_dataframe(df, options=options)

    # Build schema manifest — 5 sample rows per column.
    sample_rows = cleaned.head(5)
    columns_schema = [
        ColumnSchema(
            alias=alias,
            original_name=mapping[alias],
            dtype=str(cleaned[alias].dtype),
            sample_values=[None if pd.isna(v) else str(v) for v in sample_rows[alias].tolist()],
        )
        for alias in cleaned.columns
    ]

    manifest = SchemaManifest(
        columns=columns_schema,
        row_count=int(len(cleaned)),
        column_count=int(len(cleaned.columns)),
        original_columns=mapping,
        preview=_build_preview(cleaned, mapping),
    )

    return IngestResult(
        df=cleaned,
        schema=manifest,
        cleaning_report=report,
        load=loaded,
        raw_row_count=raw_row_count,
    )
