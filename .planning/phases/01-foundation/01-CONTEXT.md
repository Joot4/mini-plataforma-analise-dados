# Phase 1: Foundation - Context

**Gathered:** 2026-04-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Entregar o skeleton do projeto (layout, `uv`, Docker, docker-compose, Dockerfile multi-stage), a camada de autenticação (registro via email/senha + login JWT + proteção de rotas + isolamento cross-user), as migrations SQLite via alembic rodando no startup, e o baseline de task registry em memória. Cobre **AUTH-01..04** + **OPS-04..06**. Fora do escopo: upload, limpeza de dados, DuckDB, LLM, NL Q&A, summary — tudo isso vem nas fases 2-5.

</domain>

<decisions>
## Implementation Decisions

### Error Response Format

- **D-01:** Envelope de erro padrão para toda API: `{error_type: string, message: string, details?: object}`. Exception handlers registrados no `app/main.py` convertem `HTTPException`, `RequestValidationError`, e exceções de domínio pra esse envelope.
- **D-02:** Idioma híbrido: `error_type` em `snake_case` inglês (contrato estável, ex.: `invalid_credentials`, `email_already_exists`, `validation_failed`); `message` sempre em **PT-BR** amigável pro usuário. Isso bate com a narração PT do resto do produto sem quebrar buscabilidade técnica.
- **D-03:** Erros de validação pydantic são transformados num `details.fields[]` com shape `{field: string, msg: string}` — front consegue destacar o campo errado. Nunca expor `loc`/`type` crus do pydantic.
- **D-04:** Stack traces só aparecem no body da resposta HTTP quando `DEBUG=true` (variável de ambiente controlada pelo Settings). Em produção `DEBUG=false` zera qualquer trace no body — detalhes vão só pros logs estruturados (stdout).

### Project Structure

- **D-05:** Layout **tech-layered**:
  ```
  app/
    __init__.py
    main.py              # FastAPI app, middleware, exception handlers, router mount
    api/
      __init__.py
      deps.py            # Shared FastAPI dependencies (get_current_user, get_db_session, etc.)
      v1/
        __init__.py
        auth.py          # /auth/register, /auth/login
        health.py        # /health (readiness probe)
    core/
      __init__.py
      config.py          # Settings (pydantic-settings)
      security.py        # JWT encode/decode + password hashing helpers (pwdlib wrapper)
      logging.py         # structlog config
    db/
      __init__.py
      session.py         # async SQLAlchemy engine + session factory
      models.py          # SQLAlchemy User model (and future tables)
      migrations/        # alembic env.py + versions/
    schemas/
      __init__.py
      auth.py            # Pydantic schemas: RegisterRequest, LoginRequest, TokenResponse, UserOut
      errors.py          # ErrorResponse envelope schema
    services/
      __init__.py
      auth_service.py    # register_user(), authenticate_user()
    tasks/
      __init__.py
      registry.py        # In-memory task_store: dict[str, TaskStatus] (baseline; usado pela Phase 2)
  tests/
    __init__.py
    api/
      test_auth.py
    services/
      test_auth_service.py
    core/
      test_security.py
    conftest.py          # fixtures (test_client, db_session, register_user factory)
  ```
  Pastas futuras (`app/llm/`, `app/duckdb_/`, `app/ingestion/`) são adicionadas pelas fases 2-5 — não criar vazias agora.

- **D-06:** Config em `app/core/config.py` via `Settings(BaseSettings)` do `pydantic-settings`. Lê de `.env` + env vars (env override vence). Singleton exposto via `@lru_cache` em `get_settings()`. Campos mínimos: `DATABASE_URL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM` (default `HS256`), `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (default `30`), `DEBUG` (default `false`), `OPENAI_API_KEY` (já definido pra fases seguintes), `UPLOADS_DIR` (default `/data/uploads`), `MAX_UPLOAD_BYTES`, `MAX_UPLOAD_ROWS`, `SESSION_TTL_SECONDS`. `.env.example` commitado; `.env` no `.gitignore`.

- **D-07:** Dependencies FastAPI compartilhadas ficam em `app/api/deps.py` num único arquivo. Inclui no v1: `get_db_session()`, `get_current_user()` (decodifica JWT, busca user no DB, 401 se inválido), `get_settings()`. Quando crescer, refatora — mas começamos centralizado.

- **D-08:** Testes em `tests/` **espelhando a estrutura de `app/`**: `tests/api/test_auth.py` testa rotas, `tests/services/test_auth_service.py` testa service layer, `tests/core/test_security.py` testa helpers de segurança. `conftest.py` raiz com fixtures compartilhadas (async test client via `httpx.AsyncClient`, in-memory SQLite pra cada teste, factory pra criar usuários). Não dividir em `unit/integration/e2e` — `pytest.mark` resolve quando precisar.

### Claude's Discretion

Decisões operacionais com defaults já alinhados com a research — downstream (plan/execute) pode seguir sem perguntar:

- **JWT:** access token **somente** (sem refresh token no v1). TTL 30 min. Algoritmo `HS256`. Transport: header `Authorization: Bearer <token>` (não cookie — é API-only, sem risco de CSRF). Biblioteca: `PyJWT ^2.12`.
- **Password hashing:** `pwdlib[bcrypt]` com cost factor default. Helper em `app/core/security.py`: `hash_password(plain) -> str`, `verify_password(plain, hashed) -> bool`.
- **Email verification:** **FORA do v1.** Informal 2-3 users não justifica infra SMTP. Fica pra v2 quando subir pra VPS/SaaS.
- **Registro:** email (pydantic `EmailStr`) + senha mínima (≥8 chars, pelo menos 1 letra e 1 dígito — validação via pydantic `field_validator`). Email normalizado pra lowercase antes de salvar/comparar. Duplicado retorna `409 Conflict` com `error_type: email_already_exists`.
- **Users table (SQLAlchemy):** `id: UUID4 (pk, default uuid4)`, `email: str (unique, indexed)`, `password_hash: str`, `created_at: datetime (default now, UTC)`, `updated_at: datetime (onupdate now)`, `is_active: bool (default true)`. Usar `Mapped[]` typing style do SQLAlchemy 2.x.
- **Task registry:** `dict[str, TaskStatus]` em memória global no módulo `app/tasks/registry.py`. TaskStatus é dataclass/pydantic com `task_id: UUID4`, `status: Literal['pending','running','done','error']`, `created_at`, `updated_at`, `progress: int (0-100)`, `result: Any`, `error_type: str | None`, `message: str | None`. Sobrevive reinício? **Não** — é aceitável (sessão one-shot já é o modelo). Baseline nessa fase; Phase 2 usa.
- **Logging:** `structlog` configurado em `app/core/logging.py`. Output JSON pra stdout. Middleware em `app/main.py` adiciona `request_id: uuid4` no context de cada request e loga `request.start` / `request.end` com latência. Padrão field keys: `event`, `timestamp`, `level`, `request_id`, `user_id?`.
- **Docker (Dockerfile):** multi-stage. Stage `builder`: `python:3.12-slim`, instala `uv`, `uv sync --frozen --no-dev`, gera `/app/.venv`. Stage `runtime`: `python:3.12-slim`, copia só `/app/.venv` + código; user não-root (`appuser`); `ENTRYPOINT` roda `alembic upgrade head` + `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Alvo < 500MB. Sem curl/build-essential no runtime.
- **Docker Compose:** 1 serviço só (`api`). Volumes: `./data/db:/db` (SQLite file), `./data/uploads:/data/uploads` (já preparado pra Phase 2). `.env` via `env_file:`. Porta 8000 exposta. `docker compose up --build` em < 10s no 2o build.
- **Alembic:** `alembic.ini` aponta pra `app/db/migrations/`. `env.py` lê `DATABASE_URL` do `Settings` (não hardcoded). Migration inicial gera tabela `users` via `--autogenerate`. Entrypoint do container roda `alembic upgrade head` antes de subir uvicorn.
- **pyproject.toml (uv):** `project.dependencies` trava versões conforme `research/STACK.md`. Dev deps em `[dependency-groups.dev]`: pytest, pytest-asyncio, httpx, respx, ruff, mypy. Scripts via `uv run`: `uv run pytest`, `uv run alembic upgrade head`, `uv run uvicorn app.main:app --reload`.
- **Lint/type:** ruff + mypy configurados em `pyproject.toml`. ruff com regras sensatas (E, W, F, I, B, UP). mypy em `strict = false` no v1 (subir pra strict numa fase de hardening).
- **.gitignore:** `.venv`, `__pycache__`, `.env`, `data/db/*.sqlite*`, `data/uploads/*`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`.
- **Health endpoint:** `GET /health` → `{status: 'ok', version: '0.1.0'}`; não precisa auth; pra liveness probe.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level context

- `.planning/PROJECT.md` — Core value, stack locked, key decisions, evolution rules
- `.planning/REQUIREMENTS.md` — 45 requisitos v1 (Phase 1 cobre AUTH-01..04 + OPS-04..06)
- `.planning/ROADMAP.md` §Phase 1 — Goal + 5 success criteria pra esta fase

### Research

- `.planning/research/STACK.md` — Versões pinnadas críticas (FastAPI 0.136.1, pydantic 2.13.3, pwdlib 0.3.0, PyJWT 2.12.1, uvicorn 0.46.0, SQLAlchemy, alembic), pwdlib vs passlib deprecation, uv workflow, Dockerfile patterns
- `.planning/research/ARCHITECTURE.md` — Module layout canônico 2026, padrão de `app/api/deps.py`, FastAPI lifespan/startup/shutdown
- `.planning/research/PITFALLS.md` — Password hashing (passlib is dead), JWT secret from env (nunca hardcoded), UUID4 session IDs (não incrementais), Docker volume mount (arquivos somem no restart), cross-user isolation no dependency layer
- `.planning/research/FEATURES.md` §Auth — Expectations de auth PT-BR (email+senha, sessão isolada)
- `.planning/research/SUMMARY.md` — Cross-cutting themes + 5 correções a PROJECT.md (passlib→pwdlib, pandas 3.0 CoW, structured output, DuckDB lockdown, per-session DuckDB)

### Project guide

- `CLAUDE.md` — Dev conventions, non-negotiable security rules, PT-BR locale, GSD workflow

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **Nenhum** — projeto greenfield, primeira fase. Tudo é criado nesta fase.

### Established Patterns

- Nenhum ainda — o layout tech-layered definido em D-05 **é** o padrão estabelecido por esta fase. Fases 2-5 devem seguir:
  - Rotas HTTP em `app/api/v{N}/`
  - Lógica de negócio em `app/services/`
  - Pydantic I/O em `app/schemas/`
  - SQLAlchemy models em `app/db/models.py`
  - Deps compartilhadas em `app/api/deps.py`
  - Exception handlers e middleware em `app/main.py`

### Integration Points

- Cada rota protegida futura (upload, query) usa `Depends(get_current_user)` de `app/api/deps.py`
- Cada operação de DB usa `Depends(get_db_session)` (async session factory em `app/db/session.py`)
- Background tasks da Phase 2 usam `app/tasks/registry.py` (criado aqui como baseline)
- Logging estruturado via `app/core/logging.py` é consumido por toda chamada LLM futura (OPS-03 na Phase 4)

</code_context>

<specifics>
## Specific Ideas

- **Consistência de idioma:** usuário explicitamente quer mensagens de erro em PT-BR pra bater com a narração PT-BR do resto do produto (summary + NL answers). O `error_type` em inglês snake_case é compromisso: mantém contrato estável/buscável pro código sem quebrar a consistência visual pro usuário final.
- **"Tech-layered, não domain-driven":** o projeto é pequeno o suficiente (6 fases, 45 reqs) pra que o overhead de domain-driven (cada feature com sua pasta, repetindo routes/services/schemas) não compense. Se crescer muito pra frente, refatorar é fácil — a direção oposta (domain → tech) é muito mais dolorida.
- **Health endpoint desde Phase 1:** pequeno detalhe mas facilita testes de integração e futura orquestração.

</specifics>

<deferred>
## Deferred Ideas

Ideias que surgiram no escopo mas pertencem a fases posteriores ou ao v2:

- **Refresh tokens + rotação** → v2 SaaS (quando sessão JWT de 30min ficar incomodando usuários reais)
- **Email verification + SMTP** → v2 SaaS (informal 2-3 users não justifica infra)
- **Rate limiting formal** → v2 SaaS (filesize cap + auth já cobrem no v1)
- **OAuth/SSO (Google, GitHub)** → v2 SaaS
- **Password reset por email** → v2 SaaS (depende de SMTP)
- **User profile endpoints (`GET /me`, `PATCH /me`)** → podem entrar numa fase posterior se necessário
- **Observabilidade avançada (Sentry, OpenTelemetry)** → v2 quando subir pra VPS
- **Admin endpoints / roles** → v2 multi-tenant
- **Task registry persistente (Redis ou DB)** → v2; in-memory é aceitável pra v1 local (sessão one-shot)

</deferred>

---

*Phase: 01-foundation*
*Context gathered: 2026-04-24*
