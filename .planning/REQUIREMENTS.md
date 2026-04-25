# Requirements: Mini Plataforma de Análise de Dados

**Defined:** 2026-04-24
**Core Value:** O usuário sobe um CSV/Excel e consegue, em poucos segundos, um resumo automático do dataset e respostas em português para perguntas livres sobre os dados, com texto + tabela + gráfico — sem escrever nada além da pergunta.

## v1 Requirements

Requisitos para a entrega inicial. Cada um mapeia para uma fase do roadmap.

### Autenticação & Sessão

- [x] **AUTH-01**: Usuário pode criar conta com email e senha (senha hashada com `pwdlib[bcrypt]`)
- [x] **AUTH-02**: Usuário pode fazer login e receber token JWT de acesso
- [x] **AUTH-03**: Endpoints protegidos rejeitam requests sem token válido (401)
- [x] **AUTH-04**: Cada sessão/upload é isolada por `user_id` — usuário A não acessa dados do usuário B
- [x] **AUTH-05**: Sessão one-shot com TTL: dataset vive em memória até 1h sem atividade, depois é expelido
- [x] **AUTH-06**: Background sweeper roda a cada 5 min e faz cleanup de sessões expiradas (libera memória)

### Ingestão

- [x] **INGEST-01**: Endpoint recebe upload `.csv` / `.xlsx` / `.tsv` via multipart e retorna `task_id` imediatamente
- [x] **INGEST-02**: Limite enforçado: rejeita (HTTP 413) arquivos > 50MB OU > 500k linhas com mensagem em PT-BR
- [x] **INGEST-03**: CSV — auto-detecta delimitador (`,` vs `;`) via sniffing na primeira linha
- [x] **INGEST-04**: CSV — auto-detecta encoding com ordem de tentativa: UTF-8 → CP1252 → Latin-1; fallback com `charset-normalizer`
- [x] **INGEST-05**: XLSX — lê primeira aba via openpyxl; ignora demais com warning no relatório
- [x] **INGEST-06**: Detecção de formato numérico PT-BR: se >60% dos valores de uma coluna casam com `^\d{1,3}(\.\d{3})*(,\d+)?$`, coluna é marcada PT-BR e convertida (remove `.` de milhar, troca `,` por `.`)
- [x] **INGEST-07**: Detecção de formato de data: default `dayfirst=True` (DD/MM/YYYY); `dateformat='%d/%m/%Y'` na carga DuckDB
- [x] **INGEST-08**: Nomes de coluna com acento/espaço/símbolos são normalizados para aliases ASCII snake_case (via `unicodedata.normalize('NFKD', ...)`); mapping `{alias → original}` é persistido no schema manifest da sessão
- [x] **INGEST-09**: Schema manifest da sessão guarda: colunas com nome original + alias + tipo detectado + 3-5 linhas de amostra

### Limpeza

- [x] **CLEAN-01**: Pipeline de limpeza aplica 4 transformações com flags opcionais no request (default `true` em todas):
  - Normalização de tipos (incluindo PT-BR números/datas)
  - Tratamento de nulos (preenche com `mean` em num, sentinela em texto, ou mantém NaN conforme config)
  - Remoção de duplicatas exatas
  - Padronização de texto (trim + lowercase em colunas categóricas)
- [x] **CLEAN-02**: Relatório de limpeza sempre retornado: `{nulos_preenchidos: N, duplicatas_removidas: M, tipos_convertidos: [...], colunas_pt_br_normalizadas: [...], textos_padronizados: [...]}`
- [x] **CLEAN-03**: Linhas/colunas 100% vazias são removidas silenciosamente (marcadas no relatório)
- [x] **CLEAN-04**: Pipeline usa pandas 3.0 com Copy-on-Write (só `.loc[]`, nada de chained assignment); string dtype é `StringDtype`, não `object`

### Resumo automático

- [x] **SUM-01**: Após limpeza, gera stats estruturados: `{rows, cols, columns: [{alias, label, type, null_pct, unique, stats: {min/max/mean/median OR top5}}]}`
- [x] **SUM-02**: Gera narração em PT-BR (2-3 parágrafos) via LLM: descreve o dataset, destaca o que chama atenção, sinaliza flags de qualidade
- [x] **SUM-03**: Resumo completo é retornado em JSON pelo endpoint de status assim que o task termina

### NL Query

- [x] **NLQ-01**: Endpoint recebe `{session_id, question}` em PT-BR e retorna `{text, table, chart_spec, generated_sql, error?}`
- [x] **NLQ-02**: Classificador de off-topic: LLM primeiro decide se a pergunta é sobre os dados da sessão; se não, retorna erro `out_of_scope` com mensagem amigável em PT-BR
- [x] **NLQ-03**: Prompt construído com: schema manifest (aliases + tipos + 3-5 linhas sample) + pergunta do usuário; NUNCA inclui o dataset completo
- [x] **NLQ-04**: LLM chamado via `AsyncOpenAI.chat.completions.parse()` com Pydantic `SQLResponse(sql: str, reasoning: str)` como `response_format` (structured output)
- [x] **NLQ-05**: Retry 1x automático se SQL retornado for inválido (reinjeta schema + erro no prompt); após 2ª falha retorna `invalid_question` pedindo reformulação
- [x] **NLQ-06**: Resultado DuckDB é convertido em `table: {columns, rows}`; se > 1000 linhas, trunca para 1000 com flag `truncated: true`
- [x] **NLQ-07**: Narração da resposta (1-3 frases em PT-BR explicando o resultado) é gerada por LLM num segundo call com o resultado estruturado
- [x] **NLQ-08**: Campo `generated_sql` sempre retornado no envelope (transparência/explicabilidade — usuário pode conferir)
- [x] **NLQ-09**: Tipo de gráfico é escolhido por heurística determinística em Python baseada no AST da SQL + shape do resultado:
  - 1 categórica + 1 numérica → `bar`
  - coluna de data + numérica → `line`
  - 2 numéricas → `scatter`
  - 1 categórica com ≤5 valores + 1 numérica com agregação → `pie` (opcional)
  - outros → só tabela, `chart_spec = null`
- [x] **NLQ-10**: `chart_spec` é JSON compatível com Vega-Lite v6 (emitido via Altair `to_dict()` server-side — valida o schema antes de retornar)

### Segurança SQL

- [x] **SQL-01**: SQL gerada pelo LLM passa por validação AST (`sqlglot.parse_one(..., read="duckdb")`): rejeita se não for `exp.Select`
- [x] **SQL-02**: Validação AST rejeita funções fora da whitelist (blocklist explícito: `read_csv`, `read_parquet`, `read_json`, `COPY`, `ATTACH`, `INSTALL`, `LOAD`, `pragma_*`, funções de I/O)
- [x] **SQL-03**: Cada sessão tem sua própria `duckdb.connect()` dedicada (não compartilhada entre requests/usuários)
- [x] **SQL-04**: Toda conexão DuckDB é hardened na criação: `SET enable_external_access = false; SET autoload_known_extensions = false; SET lock_configuration = true`
- [x] **SQL-05**: Queries pandas/DuckDB rodam em `run_in_executor` para não bloquear o event loop do FastAPI

### Operações

- [x] **OPS-01**: Background task usa `BackgroundTasks` do FastAPI + registry em memória (`dict[task_id → TaskStatus]`); endpoint `GET /tasks/{task_id}` retorna status `pending | running | done | error` + progresso + resultado quando pronto
- [x] **OPS-02**: Arquivo uploadado é persistido em volume Docker `/data/uploads/{user_id}/{task_id}` durante o processamento; deletado ao fim da TTL da sessão
- [x] **OPS-03**: Log estruturado (JSON, stdout) de cada chamada LLM: `{provider, model, tokens_in, tokens_out, cost_estimated, latency_ms, session_id}`
- [x] **OPS-04
**: Docker Compose local com volume pra `/data` e `/db` (SQLite); sobe com `docker compose up` em <10s
- [x] **OPS-05
**: Dockerfile multi-stage usando imagem `python:3.12-slim` + `uv` — imagem final < 500MB
- [x] **OPS-06
**: Migrations SQLite (users, sessions) via alembic, rodam no startup

### Performance

- [ ] **PERF-01**: Arquivo CSV PT-BR de 80k linhas: limpeza + resumo em ≤30s (cenário "v1 pronto")
- [ ] **PERF-02**: Pergunta NL sobre dataset carregado: resposta em ≤10s (inclui chamadas ao LLM)

## v2 Requirements

Adiados pra depois do v1. Conhecidos mas não no roadmap atual.

### Multi-turn & UI

- **UI-01**: Frontend web (React ou Streamlit) consumindo a API do v1
- **NLQ-V2-01**: Conversa multi-turn: últimas 3 perguntas + respostas injetadas no prompt da próxima (follow-up contextual)
- **NLQ-V2-02**: Sugestão automática de próximas perguntas ("perguntas sugeridas" após cada resposta)

### Ingestão

- **INGEST-V2-01**: Seletor de aba em XLSX (múltiplas abas)
- **INGEST-V2-02**: Suporte a `.xls` (formato binário antigo)
- **INGEST-V2-03**: Preview das primeiras 20 linhas antes de processar (confirma tipos detectados)

### Produto/SaaS

- **SAAS-01**: Deploy em VPS (Hostinger + Easypanel) com túnel pra acesso da equipe
- **SAAS-02**: Histórico persistente de uploads (opt-in explícito pelo usuário)
- **SAAS-03**: Multi-file joins (upload de 2+ arquivos relacionáveis)
- **SAAS-04**: Rate limiting por usuário

### Qualidade de IA

- **QA-V2-01**: Avaliação de PT-BR narrativa com dataset de benchmark (Ragas ou similar)
- **QA-V2-02**: Fuzzy deduplicação (embeddings + threshold)
- **QA-V2-03**: A/B entre modelos (GPT-4o-mini vs GPT-4o vs Claude Haiku)

## Out of Scope

Explicitamente excluídos. Documentado pra prevenir scope creep.

| Feature | Motivo |
|---------|--------|
| Frontend/UI no v1 | API-first confirmado; valida o core antes de gastar em UI |
| Histórico persistente de uploads | Sessão one-shot é decisão arquitetural; histórico vira LGPD/backup/UI — fora do v1 |
| LLM executa pandas/Python arbitrário | Risco de RCE; sandbox exige infra inviável pro v1 local. LLM só gera SELECT validado |
| LLM escolhe tipo de gráfico | Não-determinístico, intestável; heurística por shape do resultado é reproduzível |
| Dashboards / refresh agendado | Requer scheduler, storage persistente, render service — fora de escopo de v1 API |
| Multi-file joins | Schema disambiguation complexa; prompt bloat; session model quebra |
| Confidence scores do LLM | LLMs calibram confiança mal; mostrar o SQL gerado é transparência melhor |
| Fuzzy deduplicação | Requer embedding model; subjetivo; v2 |
| Múltiplas abas XLSX | Primeira aba no v1; seletor vira parâmetro no v2 |
| XLS antigo (.xls) | Formato binário legado; XLSX cobre 99% dos casos reais |
| WebSocket/SSE de progresso | Polling resolve a UX; streaming é complexidade desnecessária |
| Rate limiting formal | 2-3 usuários informais não justificam; file size cap + auth já cobrem |
| Postgres ou storage externo | SQLite cobre users/sessões no v1; upgrade vira v2 quando deploy em VPS |
| Deploy em servidor | V1 local-only confirmado; VPS é fase posterior |
| OAuth/SSO | Email+senha é suficiente pro v1 |
| passlib (usar pwdlib) | Biblioteca morta desde 2020; FastAPI migrou pra pwdlib oficialmente |

## Traceability

Mapa de qual fase cobre qual requisito. Populado durante a criação do roadmap.

| Requirement | Phase | Status |
|-------------|-------|--------|
| AUTH-01 | Phase 1 | Foundation done (01-02 helpers + 01-03 User table) |
| AUTH-02 | Phase 1 | Foundation done (01-02) |
| AUTH-03 | Phase 1 | Foundation done (01-02) |
| AUTH-04 | Phase 1 | Foundation done (01-03 — User UUID4 PK + Settings-driven DB) |
| AUTH-05 | Phase 3 | Done (03-shipped) |
| AUTH-06 | Phase 3 | Done (03-shipped) |
| INGEST-01 | Phase 2 | Done (02-shipped) |
| INGEST-02 | Phase 2 | Done (02-shipped) |
| INGEST-03 | Phase 2 | Done (02-shipped) |
| INGEST-04 | Phase 2 | Done (02-shipped) |
| INGEST-05 | Phase 2 | Done (02-shipped) |
| INGEST-06 | Phase 2 | Done (02-shipped) |
| INGEST-07 | Phase 2 | Done (02-shipped) |
| INGEST-08 | Phase 2 | Done (02-shipped) |
| INGEST-09 | Phase 2 | Done (02-shipped) |
| CLEAN-01 | Phase 2 | Done (02-shipped) |
| CLEAN-02 | Phase 2 | Done (02-shipped) |
| CLEAN-03 | Phase 2 | Done (02-shipped) |
| CLEAN-04 | Phase 2 | Done (02-shipped) |
| SUM-01 | Phase 4 | Done (04-shipped) |
| SUM-02 | Phase 4 | Done (04-shipped) |
| SUM-03 | Phase 4 | Done (04-shipped) |
| NLQ-01 | Phase 5 | Done (05-shipped) |
| NLQ-02 | Phase 5 | Done (05-shipped) |
| NLQ-03 | Phase 5 | Done (05-shipped) |
| NLQ-04 | Phase 5 | Done (05-shipped) |
| NLQ-05 | Phase 5 | Done (05-shipped) |
| NLQ-06 | Phase 5 | Done (05-shipped) |
| NLQ-07 | Phase 5 | Done (05-shipped) |
| NLQ-08 | Phase 5 | Done (05-shipped) |
| NLQ-09 | Phase 5 | Done (05-shipped) |
| NLQ-10 | Phase 5 | Done (05-shipped) |
| SQL-01 | Phase 3 | Done (03-shipped) |
| SQL-02 | Phase 3 | Done (03-shipped) |
| SQL-03 | Phase 3 | Done (03-shipped) |
| SQL-04 | Phase 3 | Done (03-shipped) |
| SQL-05 | Phase 3 | Done (03-shipped) |
| OPS-01 | Phase 2 | Done (02-shipped) |
| OPS-02 | Phase 2 | Done (02-shipped) |
| OPS-03 | Phase 4 | Done (04-shipped) |
| OPS-04 | Phase 1 | Done (01-01) |
| OPS-05 | Phase 1 | Done (01-01 image scaffold + 01-03 alembic stack) |
| OPS-06 | Phase 1 | Done (01-01 + 01-03 alembic upgrade head wired) |
| PERF-01 | Phase 6 | Pending |
| PERF-02 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 45 total
- Mapped to phases: 45 ✓
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-24*
*Last updated: 2026-04-24 after roadmap creation*
