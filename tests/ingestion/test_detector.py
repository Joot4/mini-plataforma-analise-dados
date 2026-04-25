from __future__ import annotations

import pandas as pd
import pytest

from app.ingestion.detector import (
    detect_delimiter,
    detect_encoding,
    is_date_series,
    is_ptbr_number_series,
    parse_date_series,
    parse_ptbr_number_series,
)


# --- Encoding ---


def test_detects_utf8() -> None:
    assert detect_encoding("Região".encode("utf-8")) == "utf-8"


def test_detects_cp1252() -> None:
    # "Região" in CP1252 has a byte (0xE3) that's invalid in UTF-8.
    raw = "Região".encode("cp1252")
    with pytest.raises(UnicodeDecodeError):
        raw.decode("utf-8")
    assert detect_encoding(raw) in {"cp1252", "latin-1"}


def test_detects_utf8_sig_bom() -> None:
    raw = b"\xef\xbb\xbf" + "Nome".encode("utf-8")
    assert detect_encoding(raw) == "utf-8-sig"


# --- Delimiter ---


def test_detects_comma_delimiter() -> None:
    sample = "a,b,c\n1,2,3\n4,5,6"
    assert detect_delimiter(sample) == ","


def test_detects_semicolon_delimiter() -> None:
    sample = "a;b;c\n1;2;3\n4;5;6"
    assert detect_delimiter(sample) == ";"


def test_semicolon_wins_when_both_present() -> None:
    # Row with a comma inside one field but ; as true delimiter — common in PT-BR.
    sample = "nome;descricao;preco\nAlice;Doce, salgado;5,99\nBob;Bala;1,50"
    assert detect_delimiter(sample) == ";"


# --- PT-BR numbers ---


def test_is_ptbr_number_series_detects_br_format() -> None:
    s = pd.Series(["1.234,56", "R$ 2.500,00", "99,90", "750,00"])
    assert is_ptbr_number_series(s) is True


def test_is_ptbr_number_series_rejects_plain_ints() -> None:
    s = pd.Series(["100", "200", "300"])
    assert is_ptbr_number_series(s) is False


def test_parse_ptbr_numbers() -> None:
    s = pd.Series(["1.234,56", "R$ 2.500,00", "99,90"])
    parsed = parse_ptbr_number_series(s)
    assert list(parsed) == [1234.56, 2500.0, 99.9]


# --- Dates ---


def test_is_date_series_detects_ddmmyyyy() -> None:
    s = pd.Series(["15/07/2024", "03/02/2024", "21/11/2023"])
    assert is_date_series(s) is True


def test_parse_dates_with_day_greater_than_12_stays_ddmm() -> None:
    s = pd.Series(["15/07/2024", "03/02/2024", "21/11/2023"])
    parsed, unambiguous = parse_date_series(s)
    assert unambiguous is True
    assert parsed.dt.day.tolist() == [15, 3, 21]
    assert parsed.dt.month.tolist() == [7, 2, 11]
