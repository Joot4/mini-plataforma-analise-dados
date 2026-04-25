# Mini Plataforma de Análise de Dados

API-only PT-BR data analysis backend: upload CSV/XLSX/TSV → automatic summary + natural-language Q&A with text + table + Vega-Lite chart spec.

## Quick start

    cp .env.example .env
    # edit .env — set JWT_SECRET_KEY (see comment in file)
    uv sync
    uv run alembic upgrade head
    uv run uvicorn app.main:app --reload

## Docker

    docker compose up --build

See `.planning/` for full project spec (ROADMAP, REQUIREMENTS, PROJECT, research).
