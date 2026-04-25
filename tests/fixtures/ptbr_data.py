"""PT-BR fixture factories.

Generates in-memory CSV/XLSX bytes with real-world BR quirks baked in:
- CP1252 encoding
- Semicolon delimiter
- "1.234,56" number format
- DD/MM/YYYY dates with day > 12
- Accented column names
- Blank rows + duplicate rows for the cleaning pipeline to remove
"""
from __future__ import annotations

from io import BytesIO

import openpyxl


def ptbr_csv_cp1252_semicolon() -> bytes:
    """CSV exported from Excel-BR: ; delimiter, CP1252, 1.234,56, DD/MM/YYYY.

    Contains:
    - Accented headers: Região, Descrição, Preço (R$), Data Venda
    - One value for Preço formatted as "R$ 1.234,56"
    - One value with day > 12 ("15/07/2024") to disambiguate DD/MM
    - One blank row (all empties) for CLEAN-03
    - Two identical rows for CLEAN-01 (duplicates)
    - One row with a missing field for CLEAN-01 (null fill)
    """
    lines = [
        "Região;Descrição;Preço (R$);Data Venda",
        "Sudeste;Produto A;1.234,56;15/07/2024",
        "Nordeste;Produto B;R$ 2.500,00;03/02/2024",
        "Sul;Produto C;99,90;21/11/2023",
        ";;;",  # blank row
        "Sudeste;Produto A;1.234,56;15/07/2024",  # duplicate
        "Norte;;750,00;05/01/2025",  # null Descrição
    ]
    text = "\n".join(lines) + "\n"
    return text.encode("cp1252")


def ptbr_csv_utf8_comma() -> bytes:
    """Standard UTF-8 comma-separated CSV — the 'easy' case."""
    text = (
        "name,email,age\n"
        "Alice,alice@example.com,30\n"
        "Bob,bob@example.com,25\n"
    )
    return text.encode("utf-8")


def ptbr_xlsx_with_extra_sheets() -> bytes:
    """XLSX with two sheets; only the first should be read, second recorded as ignored."""
    wb = openpyxl.Workbook()
    ws1 = wb.active
    assert ws1 is not None
    ws1.title = "Vendas"
    ws1.append(["Região", "Preço", "Data"])
    ws1.append(["Sul", "1234.56", "15/07/2024"])
    ws1.append(["Norte", "500", "03/02/2024"])

    ws2 = wb.create_sheet("Deveria Ignorar")
    ws2.append(["x", "y"])
    ws2.append([1, 2])

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def huge_row_count_csv(rows: int) -> bytes:
    """CSV with a large row count — used to trigger the 500k-row cap."""
    header = "a,b,c\n"
    row = "1,2,3\n"
    return (header + row * rows).encode("utf-8")
