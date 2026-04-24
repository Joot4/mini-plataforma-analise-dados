# Mini Plataforma de Análise de Dados

## What This Is

Ferramenta backend (API-first) que aceita upload de planilha (CSV/XLSX/TSV), limpa e agrega os dados automaticamente, gera um resumo inicial com narração em português, e responde perguntas em linguagem natural sobre o arquivo devolvendo texto + tabela + spec de gráfico. Alvo informal de uso: 2-3 pessoas do mesmo círculo (colegas, cliente próximo) — o diferencial é a explicação em linguagem natural gerada por IA em cima dos dados, sem o usuário precisar escrever uma linha de código ou SQL.

## Core Value

O usuário sobe um CSV/Excel e consegue, em poucos segundos, (a) um resumo automático do que tem ali dentro e (b) respostas em português para perguntas livres sobre os dados, com texto, tabela e gráfico — tudo sem escrever nada além da pergunta.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

<!-- Current scope. Building toward these. -->

**Autenticação & sessão**
- [ ] Login com email/senha — cada usuário só vê seus próprios uploads/sessões
- [ ] Sessão one-shot: arquivo vive em memória/volume durante a sessão ativa e é descartado ao fim (TTL 1h sem atividade)

**Ingestão**
- [ ] Upload de `.csv` com auto-detect de delimitador (`,` ou `;`) e encoding (UTF-8 + Latin-1/Windows-1252 fallback)
- [ ] Upload de `.xlsx` (primeira aba)
- [ ] Upload de `.tsv`
- [ ] Limite de arquivo: 500k linhas OU 50MB (o que vier primeiro) — rejeita acima com mensagem clara

**Processamento (background)**
- [ ] Upload retorna `task_id` imediatamente; cliente acompanha status via polling HTTP
- [ ] Limpeza automática com 4 transformações togáveis via flags (default todas `true`):
  - Normalização de tipos (detecta data/número/texto, converte formatos PT-BR como `1.234,56`)
  - Tratamento de nulos (preenche com mean/zero/sentinela conforme tipo)
  - Remoção de duplicatas
  - Padronização de texto (trim + lowercase em categorias)
- [ ] Relatório de limpeza: quantos nulos preenchidos, duplicatas removidas, tipos convertidos — sempre retornado

**Resumo automático**
- [ ] Stats estruturados: contagem linhas/colunas, tipos detectados por coluna, min/max/mean/median/% nulos por coluna numérica, top-5 valores por coluna categórica
- [ ] Narração em português gerada por LLM (2-3 parágrafos): "o que é esse dataset e o que chama atenção"

**Perguntas em linguagem natural**
- [ ] Endpoint de pergunta recebe texto em PT + `session_id`, retorna resposta estruturada
- [ ] LLM gera SELECT SQL contra tabela in-memory no DuckDB (dados do upload viram tabela DuckDB)
- [ ] Validação de SQL antes de executar: só SELECT permitido, whitelist de funções
- [ ] Classificador rejeita perguntas fora do contexto dos dados (ex.: "qual a capital do Brasil?")
- [ ] Retry 1x quando LLM gera SQL inválido; se falhar, pede reformulação
- [ ] Resposta volta em 3 partes: texto narrado em PT, tabela (linhas do resultado) e spec Vega-Lite do gráfico

**Contrato de gráfico**
- [ ] Tipo de gráfico escolhido por heurística determinística no backend (não pelo LLM):
  - 1 categórica + 1 numérica → bar
  - data + numérica → line
  - 2 numéricas → scatter
  - fallback → tabela apenas
- [ ] Output JSON compatível com [Vega-Lite](https://vega.github.io/vega-lite/) pra front renderizar com `vega-embed` quando existir

**Performance**
- [ ] Arquivo de 80k linhas: limpeza + resumo em ≤30s
- [ ] Pergunta NL em cima de dataset carregado: resposta em ≤10s (inclui chamada ao LLM)

**Observabilidade mínima**
- [ ] Log estruturado de cada chamada ao LLM (tokens in/out, custo estimado, latência)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- **Histórico persistente de uploads** — escolhido one-shot explicitamente; guardar uploads vira banco de dados, LGPD, backup, UI de histórico. Fora do escopo v1.
- **Frontend/UI** — API-first confirmado; UI vem em fase separada (provavelmente v2). Teste do v1 é via `curl`/Postman/script.
- **Deploy em servidor** — v1 roda local via Docker/OrbStack. VPS/cloud vira fase posterior só depois de validar o core.
- **Multi-tenant formal** — usuários coexistem (auth isola sessões) mas não é SaaS; sem billing, plano, ou org-level separation.
- **LLM executa código pandas arbitrário** — risco de RCE/sandbox inviável pra v1 local. LLM só gera SQL validado contra DuckDB.
- **LLM escolhe tipo de gráfico** — determinismo ganha; heurística por shape do resultado é testável, LLM-driven não é.
- **Múltiplas abas do XLSX** — pega primeira aba; seletor de aba fica pra depois.
- **XLS antigo (.xls)** — formato binário legado, exige bibliotecas extras. XLSX cobre 99%.
- **WebSocket/SSE de progresso** — polling resolve o v1; streaming vem se a UX pedir.
- **Rate limiting / anti-abuse formal** — uso informal de 2-3 pessoas não justifica a complexidade.
- **Postgres ou storage externo** — SQLite local para users/sessões é suficiente. Arquivo fica em volume Docker com TTL.

## Context

**Stack escolhida:**
- **Runtime/API:** Python 3.12 + FastAPI (async, upload nativo, background tasks)
- **Data engine:** pandas (limpeza) + DuckDB (query engine para perguntas em NL; lê CSV/Parquet direto e processa 100k+ linhas em milissegundos)
- **LLM provider:** OpenAI (GPT-4o-mini como default; trocar por GPT-4o só se qualidade exigir)
- **Auth/persistência:** SQLite para users e sessões (Postgres é overkill no v1 local)
- **Storage temporário:** volume Docker montado em `/data/uploads` com TTL de 1h
- **Package manager:** `uv` (instalação rápida, lock nativo)
- **Testes:** pytest
- **Infra local:** Docker + Docker Compose + OrbStack (já usado em outro projeto do usuário)

**Por que DuckDB + LLM gera SQL (não pandas em sandbox):**
- Segurança: só SELECT é permitido, validado antes de executar. Zero superfície de RCE.
- Token-efficient: LLM recebe só o schema da tabela + 3-5 linhas de amostra, não o dataset.
- Transparência: o SQL gerado pode ser mostrado ao usuário para explicar a resposta.
- Performance: DuckDB é um motor OLAP in-memory que supera pandas por 10-100x em agregações típicas.

**Usuário e expectativa:**
- Alvo informal: 2-3 pessoas do mesmo círculo (não é produto, não é SaaS, não é ferramenta pública).
- Dados são genéricos: qualquer Excel/CSV — o sistema não assume domínio fixo (vendas, financeiro, etc.).
- API-first: v1 não tem UI; validação é via curl/Postman. UI vai existir em outra fase.

**Experiência prévia do usuário:**
- Já domina Node/TypeScript/NestJS (outro projeto em paralelo).
- Aceitou Python/FastAPI para este projeto pelo ecossistema de dados (pandas/DuckDB).

## Constraints

- **Tech — Backend:** Python 3.12 + FastAPI — decisão amarrada para eliminar subprocess/microsserviço; tudo mono-runtime.
- **Tech — Data engine:** pandas (limpeza) + DuckDB (queries NL) — DuckDB é inegociável pela combinação segurança + performance.
- **Tech — LLM:** OpenAI GPT-4o-mini — custo-benefício alto; pode ser trocado sem reescrever o sistema se qualidade exigir.
- **Tech — Package manager:** `uv` — não usar pip/poetry diretamente; `uv` controla lock e ambiente.
- **Deploy — Local:** v1 só roda via Docker/OrbStack na máquina do dev — nenhuma dependência de infra remota (fora a API da OpenAI).
- **Segurança — LLM:** LLM jamais executa código arbitrário. Só produz SELECT validado contra whitelist de funções DuckDB.
- **Segurança — Arquivos:** uploads ficam em volume isolado por usuário; TTL de 1h após última atividade na sessão.
- **Escopo — Genérico:** sistema não assume domínio dos dados (vendas, RH, financeiro). Qualquer decisão que exija "saber o domínio" fica fora do v1.
- **Performance — Arquivo alvo:** 500k linhas / 50MB é o teto v1. Acima disso, rejeitar explicitamente.

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Backend Python puro (FastAPI) em vez de Node+Python híbrido | Uma mini-plataforma não justifica dois runtimes; pandas/DuckDB são o coração, Python é o caminho de menor atrito | — Pending |
| DuckDB + LLM-gera-SQL em vez de pandas-em-sandbox | Segurança (sem RCE), determinismo, performance, transparência (dá pra mostrar o SQL gerado) | — Pending |
| OpenAI GPT-4o-mini como LLM default | Custo-benefício alto, ótimo em text-to-SQL, já cobre a qualidade esperada para um v1 | — Pending |
| Sessão one-shot em vez de histórico persistente | Reduz drasticamente o escopo: sem banco para uploads, sem UI de histórico, sem política de retenção/LGPD | — Pending |
| API-first (sem UI no v1) | Valida o core (pipeline de ingestão → limpeza → resumo → NL) sem gastar esforço em UI que pode mudar depois | — Pending |
| Vega-Lite como contrato de gráfico | Spec declarativa, aberta, renderizável por qualquer biblioteca front amanhã (vega-embed, Altair-like) | — Pending |
| Heurística determinística escolhe tipo de gráfico (não o LLM) | Testável, reproduzível; LLM-escolhe introduz não-determinismo num lugar onde não precisa | — Pending |
| SQLite em vez de Postgres | Escopo (users + sessões) é pequeno; Postgres adiciona infra sem ganho no v1 local | — Pending |
| Background task + polling (não WebSocket/SSE) | Polling resolve o UX esperado; streaming de progresso é complexidade desnecessária no v1 | — Pending |
| `uv` como package manager | Instalação rápida, lock nativo, padrão Python moderno | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-24 after initialization*
