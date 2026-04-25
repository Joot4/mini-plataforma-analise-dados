"""Unified file reader: dispatches to CSV or XLSX parsers based on suffix.

All paths return (DataFrame, load_metadata) where load_metadata records which
format/encoding/delimiter was used so the cleaning report can surface it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import pandas as pd

from app.ingestion.detector import (
    detect_delimiter,
    detect_encoding,
    read_csv_bytes_with_encoding,
)


@dataclass
class LoadResult:
    df: pd.DataFrame
    format: str  # "csv" | "tsv" | "xlsx"
    encoding: str | None = None
    delimiter: str | None = None
    sheets_ignored: list[str] = field(default_factory=list)


class UnsupportedFormatError(Exception):
    """Raised when the file suffix is not one of .csv, .tsv, .xlsx."""


class EmptyFileError(Exception):
    """Raised when the file parses to zero rows."""


class SingleColumnError(Exception):
    """Raised when delimiter detection produced a single column containing delimiter chars."""


def load_file(path: Path) -> LoadResult:
    """Load a file from disk based on its suffix.

    - .csv  → auto-detect encoding + delimiter
    - .tsv  → auto-detect encoding; delimiter forced to `\t`
    - .xlsx → first sheet via openpyxl; later sheets listed in sheets_ignored
    """
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return _load_xlsx(path)
    if suffix in {".csv", ".tsv"}:
        return _load_delimited(path, forced_delim="\t" if suffix == ".tsv" else None)
    raise UnsupportedFormatError(f"Formato não suportado: {suffix}. Use .csv, .tsv ou .xlsx.")


def _load_delimited(path: Path, forced_delim: str | None = None) -> LoadResult:
    raw = path.read_bytes()
    if not raw.strip():
        raise EmptyFileError("Arquivo vazio.")
    encoding = detect_encoding(raw)
    sample_text = raw[:8192].decode(encoding, errors="replace")
    delimiter = forced_delim if forced_delim is not None else detect_delimiter(sample_text)
    df = read_csv_bytes_with_encoding(raw, encoding, delimiter)

    # PT-BR safety net: if we got a single column AND the column name contains a
    # likely delimiter, re-parse with that delimiter. Excel BR is the common culprit.
    if df.shape[1] == 1:
        col = df.columns[0]
        for candidate in [";", "\t", "|"]:
            if candidate in str(col):
                df = read_csv_bytes_with_encoding(raw, encoding, candidate)
                delimiter = candidate
                break
        else:
            raise SingleColumnError(
                "Não foi possível detectar o delimitador correto; "
                "arquivo parece ter uma única coluna."
            )

    return LoadResult(
        df=df,
        format="tsv" if forced_delim == "\t" else "csv",
        encoding=encoding,
        delimiter=delimiter,
    )


def _load_xlsx(path: Path) -> LoadResult:
    raw = path.read_bytes()
    if not raw.strip():
        raise EmptyFileError("Arquivo vazio.")
    # Read ALL sheet names so we can report ignored ones.
    all_sheets = pd.read_excel(BytesIO(raw), sheet_name=None, engine="openpyxl", dtype=str)
    if not all_sheets:
        raise EmptyFileError("Planilha XLSX sem abas legíveis.")
    first_name, first_df = next(iter(all_sheets.items()))
    ignored = [name for name in all_sheets if name != first_name]
    # Normalize empty-string cells to NaN for consistent downstream handling.
    # pandas 3.0: `.str` is only a Series accessor, so apply per column.
    for col in first_df.columns:
        s = first_df[col].astype("string").str.strip()
        first_df[col] = s.where(s != "", other=pd.NA)
    return LoadResult(
        df=first_df,
        format="xlsx",
        encoding=None,
        delimiter=None,
        sheets_ignored=ignored,
    )
