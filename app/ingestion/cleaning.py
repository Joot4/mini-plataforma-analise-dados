"""Cleaning pipeline: nulls, duplicates, type coercion, string standardization.

All transforms use pandas 3.0 Copy-on-Write friendly patterns (`.loc[]` assignment
only — no chained assignment). String dtype is `StringDtype`, never `object`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.ingestion.detector import (
    is_date_series,
    is_ptbr_number_series,
    parse_date_series,
    parse_ptbr_number_series,
)


@dataclass
class CleaningReport:
    nulos_preenchidos: int = 0
    duplicatas_removidas: int = 0
    tipos_convertidos: list[str] = field(default_factory=list)
    colunas_pt_br_normalizadas: list[str] = field(default_factory=list)
    textos_padronizados: list[str] = field(default_factory=list)
    linhas_vazias_removidas: int = 0
    colunas_vazias_removidas: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "nulos_preenchidos": self.nulos_preenchidos,
            "duplicatas_removidas": self.duplicatas_removidas,
            "tipos_convertidos": self.tipos_convertidos,
            "colunas_pt_br_normalizadas": self.colunas_pt_br_normalizadas,
            "textos_padronizados": self.textos_padronizados,
            "linhas_vazias_removidas": self.linhas_vazias_removidas,
            "colunas_vazias_removidas": self.colunas_vazias_removidas,
        }


@dataclass
class CleaningOptions:
    fill_nulls: bool = True
    drop_duplicates: bool = True
    convert_types: bool = True
    standardize_text: bool = True


def clean_dataframe(
    df: pd.DataFrame, options: CleaningOptions | None = None
) -> tuple[pd.DataFrame, CleaningReport]:
    """Apply the cleaning pipeline and return (cleaned_df, report).

    Pipeline order matters:
    1. Drop 100% empty rows and columns (silent, reported).
    2. Type conversion (PT-BR numbers, dates, booleans) — BEFORE null fill so we
       don't freeze strings like "" as the fill value for numeric cols.
    3. Duplicate removal.
    4. Null fill (only on columns where it's safe).
    5. Text standardization (trim + `StringDtype`).
    """
    opts = options or CleaningOptions()
    report = CleaningReport()

    # Work on a copy so the caller's frame is untouched.
    out = df.copy()

    # 1. Drop 100% empty rows + columns.
    empty_cols = [c for c in out.columns if out[c].isna().all()]
    if empty_cols:
        report.colunas_vazias_removidas = list(empty_cols)
        out = out.drop(columns=empty_cols)
    before_rows = len(out)
    out = out.dropna(how="all")
    report.linhas_vazias_removidas = before_rows - len(out)

    # 2. Type conversion.
    if opts.convert_types:
        for col in out.columns:
            series = out[col]
            is_strish = pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)
            if not is_strish:
                continue
            if is_ptbr_number_series(series):
                out[col] = parse_ptbr_number_series(series)
                report.tipos_convertidos.append(col)
                report.colunas_pt_br_normalizadas.append(col)
                continue
            if is_date_series(series):
                parsed, _ = parse_date_series(series)
                out[col] = parsed
                report.tipos_convertidos.append(col)
                continue
            # Try plain numeric (locale-neutral) conversion.
            plain_numeric = pd.to_numeric(series, errors="coerce")
            if plain_numeric.notna().sum() > 0 and plain_numeric.notna().mean() >= 0.9:
                out[col] = plain_numeric
                report.tipos_convertidos.append(col)

    # 3. Drop exact-duplicate rows.
    if opts.drop_duplicates:
        before = len(out)
        out = out.drop_duplicates(ignore_index=True)
        report.duplicatas_removidas = before - len(out)

    # 4. Null fill — per-column strategy:
    #    - string/object → "" (so SQL filters like `coluna != ''` work)
    #    - numeric    → KEEP NaN. Filling with 0 distorts MEDIAN/AVG/etc.
    #                   DuckDB aggregates already skip NaN, and `null_pct` in
    #                   the summary then reflects true missingness.
    #    - datetime   → KEEP NaT (filling dates is almost always wrong)
    if opts.fill_nulls:
        null_count = 0
        for col in out.columns:
            null_count_before = int(out[col].isna().sum())
            if null_count_before == 0:
                continue
            series = out[col]
            if pd.api.types.is_numeric_dtype(series) or pd.api.types.is_datetime64_any_dtype(series):
                continue
            out[col] = series.fillna("")
            null_count += null_count_before
        report.nulos_preenchidos = null_count

    # 5. Text standardization: strip + `StringDtype`.
    if opts.standardize_text:
        for col in out.columns:
            series = out[col]
            if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
                out[col] = series.astype("string").str.strip()
                report.textos_padronizados.append(col)

    return out, report
