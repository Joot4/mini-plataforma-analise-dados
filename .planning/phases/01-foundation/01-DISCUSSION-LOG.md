# Phase 1: Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-24
**Phase:** 01-foundation
**Areas discussed:** Error format, Project structure
**Areas deferred to Claude's Discretion:** JWT strategy, Email verification

---

## Gray Area Selection

| Area offered | Selected |
|--------------|----------|
| Estratégia de token JWT | — (Claude's discretion) |
| Verificação de email | — (Claude's discretion) |
| Formato de erro padrão | ✓ |
| Estrutura do projeto | ✓ |

---

## Error Format

### Q: Qual formato de erro padrão pra toda API?

| Option | Description | Selected |
|--------|-------------|----------|
| Envelope custom | `{error_type, message, details?}` — simples, PT-BR amigável, fácil pro front | ✓ |
| RFC 7807 Problem Details | `{type, title, status, detail, instance}` — padrão W3C, interoperável, verboso | |
| Só FastAPI default | Default `{detail: ...}` — mínimo esforço, menos controle | |

**User's choice:** Envelope custom

### Q: Mensagens de erro em qual idioma?

| Option | Description | Selected |
|--------|-------------|----------|
| PT-BR | Usuários são BR, narração da IA é PT — consistência fecha | |
| Inglês | Padrão de dev, fácil buscar no Google, quebra consistência com produto | |
| EN interno + PT na resposta | `error_type` snake_case EN (contrato) + `message` PT-BR (UX) | ✓ (via "PT-BR" + follow-up context) |

**User's choice:** PT-BR (híbrido EN/PT aplicado no `error_type`+`message`)

### Q: Como formatar erros de validação do pydantic?

| Option | Description | Selected |
|--------|-------------|----------|
| Lista com field+msg | `details.fields[]` com `{field, msg}` — front renderiza por campo | ✓ |
| Só mensagem agregada | String concatenada — simples mas não destaca campo | |
| Formato pydantic cru | Array `loc`/`msg`/`type` — expõe detalhe interno | |

**User's choice:** Lista com field+msg

### Q: Stack trace aparece em resposta de erro?

| Option | Description | Selected |
|--------|-------------|----------|
| Só com DEBUG=true | Dev mostra trace; prod esconde, logs estruturados cobrem | ✓ |
| Nunca | Zero trace no body, ever — tudo via logs | |
| Sempre | Facilita debug mas expõe internos | |

**User's choice:** Só com DEBUG=true

---

## Project Structure

### Q: Layout principal de módulos?

| Option | Description | Selected |
|--------|-------------|----------|
| Tech-layered | `app/api/`, `app/services/`, `app/schemas/`, `app/db/`, etc. — FastAPI clássico 2026 | ✓ |
| Domain-driven | `app/auth/`, `app/upload/` — cada domínio agrupa rotas+services+models | |
| Hybrid | `app/features/{auth,upload}/` + `app/core/` | |

**User's choice:** Tech-layered

### Q: Onde fica settings/config?

| Option | Description | Selected |
|--------|-------------|----------|
| `app/core/config.py` | `Settings(BaseSettings)` pydantic-settings + `@lru_cache` | ✓ |
| `app/settings.py` na raiz | Mesmo conteúdo, layout mais plano | |
| YAML/TOML separado | Mais flexível mas menos Pythonic pra secrets | |

**User's choice:** `app/core/config.py`

### Q: Onde ficam dependencies compartilhadas?

| Option | Description | Selected |
|--------|-------------|----------|
| `app/api/deps.py` | Um arquivo central com todas as FastAPI Depends | ✓ |
| Perto do domínio | `app/services/auth/deps.py` — acopla ao service | |
| `app/dependencies/` com grupos | `auth_deps.py`, `db_deps.py` — melhor escala | |

**User's choice:** `app/api/deps.py`

### Q: Estrutura dos testes?

| Option | Description | Selected |
|--------|-------------|----------|
| `tests/` espelhando `app/` | `tests/api/test_auth.py`, etc. | ✓ |
| `tests/` flat por feature | `tests/test_auth.py`, `tests/test_upload.py` | |
| `tests/unit/integration/e2e` | Separa por tipo, mais formal | |

**User's choice:** `tests/` espelhando `app/`

---

## Claude's Discretion

Áreas onde o usuário delegou a decisão com base nos defaults da research:

- **JWT strategy:** Access-only JWT (sem refresh token no v1), TTL 30 min, HS256, Bearer header (não cookie)
- **Email verification:** Fora do v1 (2-3 users informal não justifica SMTP)
- **Password rules:** ≥8 chars, 1 letra + 1 dígito (validação pydantic)
- **Users table:** UUID4 id, email unique indexed, password_hash, created_at, updated_at, is_active
- **Task registry:** `dict[str, TaskStatus]` em memória, não sobrevive restart (aceitável pra v1 local one-shot)
- **Docker:** multi-stage Dockerfile, alvo <500MB, docker-compose com 1 serviço só
- **Alembic:** `--autogenerate` do SQLAlchemy models, roda no startup do container
- **Logging:** structlog JSON em stdout + middleware de request_id
- **Lint/type:** ruff + mypy (strict=false no v1)

## Deferred Ideas

- Refresh tokens + rotação → v2 SaaS
- Email verification + SMTP → v2 SaaS
- Rate limiting formal → v2 SaaS
- OAuth/SSO → v2 SaaS
- Password reset → v2 (depende SMTP)
- Admin roles / multi-tenant → v2
- Task registry persistente (Redis/DB) → v2
- Observabilidade (Sentry, OpenTelemetry) → v2
