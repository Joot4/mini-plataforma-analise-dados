# Mini Plataforma de Análise de Dados

Backend Python (API-only) que aceita upload de planilha (CSV/XLSX/TSV), limpa automaticamente, gera resumo com narração em PT-BR, e responde perguntas em linguagem natural sobre os dados via LLM devolvendo texto + tabela + spec Vega-Lite.

## Planning artifacts

Tudo em `.planning/`:

- `PROJECT.md` — contexto, core value, decisões-chave
- `REQUIREMENTS.md` — 45 requisitos v1 agrupados em 8 categorias (AUTH, INGEST, CLEAN, SUM, NLQ, SQL, OPS, PERF)
- `ROADMAP.md` — 6 fases, cada uma com goal, requisitos, success criteria
- `STATE.md` — estado atual do projeto (fase corrente, progresso)
- `config.json` — workflow config (yolo mode, granularity=standard, parallel, all verifications on)
- `research/` — STACK, FEATURES, ARCHITECTURE, PITFALLS, SUMMARY (ler antes de qualquer decisão técnica nova)

## Stack (locked)

| Camada | Escolha | Notas críticas |
|--------|---------|----------------|
| Runtime | Python 3.12 | mínimo exigido por pandas 3.x |
| API | FastAPI ^0.136 + uvicorn[standard] ^0.46 | async-native, pydantic v2 built-in |
| Validação | pydantic ^2.13 | |
| Dados (limpeza) | pandas ^3.0 | **CoW default** (usar só `.loc[]`, nada de chained assignment); string dtype é `StringDtype` |
| Query engine | DuckDB ^1.5 + sqlglot ^30.6 | conexão isolada por sessão; lockdown obrigatório |
| Excel | openpyxl (NÃO xlrd) | primeira aba no v1 |
| LLM | OpenAI SDK ^2.32 | `AsyncOpenAI.chat.completions.parse()` com Pydantic response_format |
| Auth | `pwdlib[bcrypt]` + PyJWT ^2.12 | **NÃO usar passlib** (abandonado em 2020) |
| Encoding | charset-normalizer ^3.4 | fallback pra detecção de CP1252/Latin-1 |
| Charts | altair ^6.1 → `to_dict()` | emite Vega-Lite v6 JSON server-side, valida schema |
| DB | SQLite + alembic | users + sessões |
| Package manager | `uv` | NÃO usar pip/poetry direto |
| Container | Docker (python:3.12-slim, multi-stage) | target < 500MB |
| Testes | pytest + httpx AsyncClient + respx | respx stub pra chamadas OpenAI |

## Non-negotiable security rules

**LLM → SQL → DuckDB:** dois layers sempre.

1. Toda SQL gerada pelo LLM passa por `sqlglot.parse_one(sql, read="duckdb")` e precisa ser `exp.Select`. Qualquer outra coisa é 400.
2. Toda conexão DuckDB (uma por sessão) é criada com:
   ```python
   con.execute("SET enable_external_access = false")
   con.execute("SET autoload_known_extensions = false")
   con.execute("SET lock_configuration = true")
   ```
3. Funções de I/O (`read_csv`, `read_parquet`, `read_json`, `COPY`, `ATTACH`, `INSTALL`, `LOAD`, `pragma_*`) estão em blocklist no validador AST, em cima da whitelist.
4. **Nunca** compartilhar conexão DuckDB entre sessões/usuários — isso causa RuntimeError não-determinístico sob concorrência.

**Event loop:** pandas e DuckDB são síncronos/CPU-bound. Sempre rodar via `await loop.run_in_executor(None, ...)` — nunca inline em `async def`.

**Passwords:** `pwdlib[bcrypt]`. Se você ver `passlib` em qualquer lugar, é bug.

## PT-BR locale — o que sempre importa

Brazilian CSVs têm 4 vetores de falha silenciosa (cada um falha sem raise):

- **Delimitador:** `;` (não `,`) — Excel-BR exporta assim
- **Encoding:** CP1252 / Latin-1 (não UTF-8) — planilhas antigas/governo
- **Número:** `1.234,56` (ponto = milhar, vírgula = decimal) — pandas lê como string
- **Data:** `DD/MM/YYYY` (não MM/DD) — pandas assume US por default

Qualquer código que lê CSV precisa tratar os 4. Fixtures de teste DEVEM cobrir pelo menos um arquivo com os 4 combinados.

Acento em nome de coluna (`Receita Bruta (R$)`, `% Inadimplência`, `Mês/Ano`) quebra SQL — normalizar pra ASCII snake_case via `unicodedata.normalize('NFKD', ...)` e manter mapping `{alias → original}` no schema manifest. LLM SEMPRE recebe aliases, nunca os nomes originais.

## GSD workflow

Este projeto é gerenciado via **GSD (Get Shit Done)**. Comandos principais:

- `/gsd-plan-phase N` — planejar a próxima fase (spawn research + planner + plan-check)
- `/gsd-execute-phase N` — executar os planos da fase N (wave-based parallel)
- `/gsd-verify-phase N` — validar se os success criteria foram atingidos
- `/gsd-progress` — onde estamos e o que vem agora
- `/gsd-next` — avança automaticamente pro próximo passo lógico

**Config atual:** YOLO mode (auto-approve), parallel execution, research + plan-check + verifier todos ligados.

**Ordem de execução:** fases sequenciais (1→2→3→4→5→6); dentro de cada fase os planos podem rodar em paralelo.

## Development conventions

- **Idioma:** código em inglês (nomes de variável, classe, função); comentários e docstrings em PT-BR só quando a regra for genuinamente específica de PT-BR; commits em inglês conforme padrão GSD
- **Estrutura:** FastAPI moderno (2026) — `app/api/`, `app/services/`, `app/schemas/`, `app/db/`, `app/llm/`, `app/duckdb_/`
- **Typing:** pydantic v2 em toda I/O; mypy strict onde fizer sentido
- **Logging:** JSON estruturado via `structlog` (saída pra stdout), nunca `print`
- **LLM call logs:** toda chamada OpenAI vira uma entrada de log com `{provider, model, tokens_in, tokens_out, cost_estimated, latency_ms, session_id}` — não-negociável

## Out of scope (v1)

Se cair uma dessas, não é pra v1 — puxar pra v2 ou rejeitar:

- Frontend/UI (API-only até v2)
- Histórico persistente de uploads (one-shot explícito)
- LLM executa código arbitrário
- LLM escolhe tipo de gráfico (heurística determinística em Python)
- Multi-file joins, múltiplas abas XLSX, XLS antigo
- Deploy em VPS/cloud
- Postgres (SQLite cobre v1)
- WebSocket/SSE (polling resolve)
