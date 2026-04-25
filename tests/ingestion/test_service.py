from __future__ import annotations

from pathlib import Path

import pytest

from app.ingestion.service import ingest_file
from tests.fixtures.ptbr_data import (
    ptbr_csv_cp1252_semicolon,
    ptbr_csv_utf8_comma,
    ptbr_xlsx_with_extra_sheets,
)


@pytest.fixture
def ptbr_csv_path(tmp_path: Path) -> Path:
    p = tmp_path / "vendas.csv"
    p.write_bytes(ptbr_csv_cp1252_semicolon())
    return p


@pytest.fixture
def utf8_csv_path(tmp_path: Path) -> Path:
    p = tmp_path / "users.csv"
    p.write_bytes(ptbr_csv_utf8_comma())
    return p


@pytest.fixture
def xlsx_path(tmp_path: Path) -> Path:
    p = tmp_path / "vendas.xlsx"
    p.write_bytes(ptbr_xlsx_with_extra_sheets())
    return p


def test_full_ptbr_csv_pipeline(ptbr_csv_path: Path) -> None:
    result = ingest_file(ptbr_csv_path)

    # Encoding detected as CP1252, delimiter as ;
    assert result.load.encoding in {"cp1252", "latin-1"}
    assert result.load.delimiter == ";"

    # Accented column names normalized to ASCII snake_case.
    aliases = [c.alias for c in result.schema.columns]
    assert "regiao" in aliases
    assert "descricao" in aliases
    assert any("preco" in a for a in aliases)
    assert "data_venda" in aliases

    # Original names preserved in mapping.
    assert "Região" in result.schema.original_columns.values()
    assert "Descrição" in result.schema.original_columns.values()

    # Preço converted to float (PT-BR number detection).
    preco_alias = next(a for a in aliases if "preco" in a)
    preco_col = result.df[preco_alias]
    assert str(preco_col.dtype).startswith("float")
    # 1234.56 must round-trip through the pipeline.
    assert 1234.56 in preco_col.tolist()
    assert 2500.0 in preco_col.tolist()

    # Data Venda parsed as datetime; 15/07/2024 must be July 15, not mangled.
    import pandas as pd

    dates = result.df["data_venda"].dropna()
    assert pd.api.types.is_datetime64_any_dtype(dates)
    months = dates.dt.month.tolist()
    days = dates.dt.day.tolist()
    # Need month 7 day 15 present somewhere — proves dayfirst=True.
    assert any(m == 7 and d == 15 for m, d in zip(months, days, strict=True))

    # Cleaning report has non-zero counts for the quirks we baked in.
    report = result.cleaning_report
    assert report.duplicatas_removidas >= 1  # the 6th row duplicates the 2nd
    assert report.linhas_vazias_removidas >= 1  # the blank row
    assert report.nulos_preenchidos >= 1  # missing Descrição on "Norte"
    assert any("preco" in c for c in report.colunas_pt_br_normalizadas)


def test_utf8_csv_simple_happy_path(utf8_csv_path: Path) -> None:
    result = ingest_file(utf8_csv_path)
    assert result.load.encoding == "utf-8"
    assert result.load.delimiter == ","
    assert result.schema.row_count == 2
    aliases = [c.alias for c in result.schema.columns]
    assert aliases == ["name", "email", "age"]


def test_xlsx_reads_first_sheet_only(xlsx_path: Path) -> None:
    result = ingest_file(xlsx_path)
    assert result.load.format == "xlsx"
    assert "Deveria Ignorar" in result.load.sheets_ignored
    aliases = [c.alias for c in result.schema.columns]
    assert "regiao" in aliases
