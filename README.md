# Mini Plataforma de Análise de Dados

Backend Python + front-end Streamlit. Upload de CSV/TSV/XLSX (com suporte PT-BR completo: CP1252, `;`, `1.234,56`, DD/MM/YYYY), resumo automático com narração, e perguntas em linguagem natural via LLM — resposta com texto + tabela + gráfico Vega-Lite.

## Quick start (dev local)

```bash
cp .env.example .env
# edite .env e preencha JWT_SECRET_KEY (dica no arquivo) e OPENAI_API_KEY

uv sync                              # dependências do backend
uv run alembic upgrade head          # roda migrations (cria users table)
uv run uvicorn app.main:app --reload # sobe a API em :8000
```

Em outro terminal, pra o frontend:

```bash
uv sync --group ui                           # instala streamlit
uv run --group ui streamlit run frontend/app.py   # :8501
```

Abra http://localhost:8501, crie conta, faça upload, pergunte.

## Docker (stack completa)

```bash
# API apenas
docker compose up --build

# API + frontend Streamlit
docker compose --profile ui up --build
```

- API: http://localhost:8000
- Frontend: http://localhost:8501

Set `OPENAI_API_KEY` no `.env` (ou via `OPENAI_API_KEY=... docker compose up`) pra habilitar a narração e o pipeline de NL Query.

## Endpoints

```
GET  /api/v1/health
POST /api/v1/auth/register       # 201 / 409
POST /api/v1/auth/login          # 200 (JWT) / 401
GET  /api/v1/auth/me             # usuário atual
POST /api/v1/upload              # 202 com task_id (limite 50MB / 500k linhas)
GET  /api/v1/upload/{id}/status  # pending | running | done | error
GET  /api/v1/sessions/{id}       # manifest da sessão
POST /api/v1/sessions/{id}/query # {question} → {text, table, chart_spec, generated_sql}
```

Docs interativos: http://localhost:8000/docs.

## Testes

```bash
uv run pytest              # 116 testes rápidos (~20s)
uv run pytest -m slow      # 2 testes de SLA (80k CSV ≤30s, NLQ ≤10s)
```

## Planning

Tudo em `.planning/`:

- `PROJECT.md` — contexto + decisões
- `REQUIREMENTS.md` — 45 requisitos v1 (todos done)
- `ROADMAP.md` — 6 fases (todas shipped)
- `STATE.md` — estado atual
- `phases/01-foundation/` — contexto, planos, verification, summaries da fase 1
- `research/` — STACK, FEATURES, ARCHITECTURE, PITFALLS, SUMMARY

## Stack

Python 3.12 · FastAPI · pydantic v2 · SQLAlchemy async + alembic · SQLite · pandas 3 · DuckDB · sqlglot · OpenAI SDK (structured output) · structlog JSON · pwdlib[bcrypt] · PyJWT · Altair (Vega-Lite v6) · Streamlit · uv · Docker multi-stage.
