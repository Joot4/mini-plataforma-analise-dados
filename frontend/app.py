"""Streamlit front-end for the Mini Plataforma de Análise de Dados API.

Single-file app. Runs with:
    uv run --group ui streamlit run frontend/app.py

Or via docker compose:
    docker compose --profile ui up

Talks to the backend at MPAD_API (default http://localhost:8000/api/v1).
"""

from __future__ import annotations

import os
import time

import httpx
import pandas as pd
import streamlit as st

API_BASE = os.environ.get("MPAD_API", "http://localhost:8000/api/v1")

st.set_page_config(
    page_title="Mini Plataforma de Análise",
    page_icon="📊",
    layout="wide",
)

# --- Session state bootstrap ---
for key, default in [
    ("token", None),
    ("email", None),
    ("session_id", None),
    ("summary", None),
    ("upload_result", None),
    ("last_query", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def api() -> httpx.Client:
    # Create a new client per call — Streamlit reruns the whole script on each
    # interaction, so holding one as module-state gains nothing.
    return httpx.Client(base_url=API_BASE, timeout=60.0)


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {st.session_state.token}"}


def api_error(body: dict) -> str:
    if not isinstance(body, dict):
        return "Erro desconhecido."
    return body.get("message") or body.get("detail") or "Erro desconhecido."


# --- Sidebar: authentication ---
with st.sidebar:
    st.header("🔐 Autenticação")
    if st.session_state.token:
        st.success(f"Logado como **{st.session_state.email}**")
        if st.button("Sair", use_container_width=True):
            for k in list(st.session_state.keys()):
                st.session_state.pop(k)
            st.rerun()
    else:
        tab_login, tab_register = st.tabs(["Entrar", "Criar conta"])
        with tab_login:
            with st.form("login", clear_on_submit=False):
                email = st.text_input("Email", key="login_email")
                password = st.text_input("Senha", type="password", key="login_pw")
                if st.form_submit_button("Entrar", use_container_width=True):
                    with api() as c:
                        r = c.post(
                            "/auth/login",
                            json={"email": email, "password": password},
                        )
                    if r.status_code == 200:
                        st.session_state.token = r.json()["access_token"]
                        st.session_state.email = email
                        st.rerun()
                    else:
                        st.error(api_error(r.json()))
        with tab_register:
            with st.form("register", clear_on_submit=False):
                email_r = st.text_input("Email", key="reg_email")
                password_r = st.text_input(
                    "Senha (mínimo 8 caracteres)", type="password", key="reg_pw"
                )
                if st.form_submit_button("Criar conta", use_container_width=True):
                    with api() as c:
                        r = c.post(
                            "/auth/register",
                            json={"email": email_r, "password": password_r},
                        )
                    if r.status_code == 201:
                        st.success("Conta criada! Faça login na outra aba.")
                    else:
                        st.error(api_error(r.json()))

    st.divider()
    st.caption(f"API: `{API_BASE}`")


# --- Main ---
st.title("📊 Mini Plataforma de Análise de Dados")
st.caption("Envie uma planilha (CSV/TSV/XLSX) em PT-BR e faça perguntas em linguagem natural.")

if not st.session_state.token:
    st.info("👈 Use o painel à esquerda para entrar ou criar uma conta.")
    st.stop()


# --- Upload step ---
if st.session_state.session_id is None:
    st.header("1. Upload da planilha")
    uploaded = st.file_uploader(
        "Envie um arquivo .csv, .tsv ou .xlsx",
        type=["csv", "tsv", "xlsx"],
    )
    if uploaded is not None:
        st.caption(
            f"📄 `{uploaded.name}` — {uploaded.size / 1024:.1f} KB "
            f"({uploaded.type or 'desconhecido'})"
        )
        if st.button("Processar arquivo", type="primary"):
            with api() as c:
                files = {
                    "file": (
                        uploaded.name,
                        uploaded.getvalue(),
                        uploaded.type or "application/octet-stream",
                    )
                }
                r = c.post("/upload", files=files, headers=auth_headers())
            if r.status_code != 202:
                st.error(api_error(r.json()))
                st.stop()

            task_id = r.json()["task_id"]
            progress_bar = st.progress(0.0, text="Enviado; processando no servidor...")
            deadline = time.time() + 120

            while time.time() < deadline:
                time.sleep(0.5)
                with api() as c:
                    s = c.get(f"/upload/{task_id}/status", headers=auth_headers())
                body = s.json()
                progress_bar.progress(
                    min(float(body.get("progress", 0.0)), 1.0),
                    text=f"Status: {body['status']}",
                )
                if body["status"] == "done":
                    st.session_state.session_id = body["result"]["session_id"]
                    st.session_state.summary = body["result"]["summary"]
                    st.session_state.upload_result = body["result"]
                    progress_bar.empty()
                    st.rerun()
                if body["status"] == "error":
                    err = body.get("error") or {}
                    st.error(
                        f"**{err.get('error_type', 'error')}**: "
                        f"{err.get('message', 'Falha no processamento.')}"
                    )
                    st.stop()
            else:
                st.error("Tempo limite excedido no processamento.")


# --- Loaded session: show summary + query UI ---
else:
    top_a, top_b = st.columns([4, 1])
    with top_a:
        st.header("Dataset carregado")
    with top_b:
        if st.button("Trocar arquivo", use_container_width=True):
            for k in (
                "session_id",
                "summary",
                "upload_result",
                "last_query",
                "messages",
                "_mirrored_session",
            ):
                st.session_state.pop(k, None)
            st.rerun()

    result = st.session_state.upload_result or {}
    summary = st.session_state.summary or {}
    cleaning = result.get("cleaning_report", {})
    load_meta = result.get("load", {})

    # --- Top metrics strip ---
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Linhas", f"{summary.get('rows', 0):,}".replace(",", "."))
    m2.metric("Colunas", summary.get("cols", 0))
    m3.metric(
        "Formato",
        f"{load_meta.get('format', '?')} / {load_meta.get('encoding') or '-'}",
    )
    m4.metric(
        "Delimitador",
        repr(load_meta.get("delimiter")) if load_meta.get("delimiter") else "-",
    )

    # --- Narration ---
    if summary.get("narration"):
        st.subheader("📝 Resumo automático")
        st.write(summary["narration"])
    elif summary.get("narration_error"):
        st.info(
            f"Narração não disponível: {summary['narration_error']}. "
            "Configure `OPENAI_API_KEY` para habilitar."
        )

    # --- Cleaning report ---
    with st.expander("🧹 Relatório de limpeza"):
        c1, c2, c3 = st.columns(3)
        c1.metric("Duplicatas removidas", cleaning.get("duplicatas_removidas", 0))
        c2.metric("Linhas vazias", cleaning.get("linhas_vazias_removidas", 0))
        c3.metric("Nulos preenchidos", cleaning.get("nulos_preenchidos", 0))
        if cleaning.get("colunas_pt_br_normalizadas"):
            st.caption(
                "Colunas PT-BR convertidas para número: "
                + ", ".join(cleaning["colunas_pt_br_normalizadas"])
            )
        if cleaning.get("tipos_convertidos"):
            st.caption("Tipos inferidos: " + ", ".join(cleaning["tipos_convertidos"]))

    # --- Column stats table ---
    with st.expander("📐 Estatísticas por coluna", expanded=True):
        rows = []
        for c in summary.get("columns", []):
            row: dict[str, object] = {
                "coluna": c["label"],
                "alias": c["alias"],
                "tipo": c["kind"],
                "nulos (%)": c["null_pct"],
                "únicos": c["unique"],
            }
            if c["kind"] == "numeric":
                row["min"] = c.get("min")
                row["max"] = c.get("max")
                row["média"] = c.get("mean")
                row["mediana"] = c.get("median")
            elif c["kind"] == "datetime":
                row["min"] = c.get("min")
                row["max"] = c.get("max")
            else:
                top = c.get("top5", [])
                row["top"] = ", ".join(f"{t['value']} ({t['freq']})" for t in top[:3])
            rows.append(row)
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.divider()

    # --- Multi-turn chat UI ---
    # `messages` is a local mirror of the server-side conversation history.
    # We prime it from the session's GET payload on first render so a page
    # reload doesn't lose the visible history.
    needs_mirror = (
        "messages" not in st.session_state
        or st.session_state.get("_mirrored_session") != st.session_state.session_id
    )
    if needs_mirror:
        st.session_state.messages = []
        st.session_state._mirrored_session = st.session_state.session_id
        try:
            with api() as c:
                sr = c.get(
                    f"/sessions/{st.session_state.session_id}",
                    headers=auth_headers(),
                )
            if sr.status_code == 200:
                for t in sr.json().get("history", []):
                    st.session_state.messages.append({"role": "user", "content": t["question"]})
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": t["text"],
                            "sql": t["sql"],
                            "row_count": t["row_count"],
                            "truncated": t.get("truncated", False),
                        }
                    )
        except Exception:
            pass

    hdr_col, reset_col = st.columns([4, 1])
    with hdr_col:
        st.header("2. Conversa sobre os dados")
    with reset_col:
        if st.session_state.messages and st.button("🧹 Limpar conversa", use_container_width=True):
            with api() as c:
                c.delete(
                    f"/sessions/{st.session_state.session_id}/conversation",
                    headers=auth_headers(),
                )
            st.session_state.messages = []
            st.session_state.last_query = None
            st.rerun()

    st.caption('💡 Follow-ups funcionam: depois de "total de vendas?", pergunte "e por região?".')

    # Render history.
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg["role"] == "assistant" and msg.get("sql"):
                meta = f"**{msg.get('row_count', '?')} linhas**"
                if msg.get("truncated"):
                    meta += " (truncado em 1000)"
                st.caption(meta)
                with st.expander("SQL"):
                    st.code(msg["sql"], language="sql")

    # Render the most-recent turn's table + chart (if any) separately so the user
    # gets a bigger view than inside the chat bubble. Older turns show only SQL.
    lq = st.session_state.last_query
    if lq:
        with st.expander("📊 Resultado da última pergunta", expanded=True):
            tab_table, tab_chart, tab_sql = st.tabs(["Tabela", "Gráfico", "SQL"])
            with tab_table:
                table = lq["table"]
                df = pd.DataFrame(table["rows"], columns=table["columns"])
                if table.get("truncated"):
                    st.caption(f"⚠️ Resultado truncado em {len(df)} linhas.")
                st.dataframe(df, use_container_width=True, hide_index=True)
                st.download_button(
                    "⬇️ Baixar CSV",
                    df.to_csv(index=False).encode("utf-8"),
                    "resultado.csv",
                    "text/csv",
                )
            with tab_chart:
                if lq.get("chart_spec"):
                    st.vega_lite_chart(lq["chart_spec"], use_container_width=True)
                else:
                    st.info("Este resultado não tem formato adequado para gráfico.")
            with tab_sql:
                st.code(lq["generated_sql"], language="sql")
                if lq.get("reasoning"):
                    st.caption(f"Raciocínio do modelo: {lq['reasoning']}")

    # Chat input — Streamlit pins it to the bottom of the page.
    question = st.chat_input("Pergunte algo sobre os dados...")
    if question:
        # Render the user message immediately, then call the API, then re-render.
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.write(question)
        with st.chat_message("assistant"):
            with st.spinner("Analisando (classificando → gerando SQL → executando → narrando)..."):
                with api() as c:
                    r = c.post(
                        f"/sessions/{st.session_state.session_id}/query",
                        json={"question": question},
                        headers=auth_headers(),
                    )
            if r.status_code == 200:
                body = r.json()
                st.session_state.last_query = body
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": body["text"],
                        "sql": body["generated_sql"],
                        "row_count": len(body["table"]["rows"]),
                        "truncated": body["table"].get("truncated", False),
                    }
                )
                st.rerun()
            else:
                body = r.json()
                err = (
                    f"**{body.get('error_type', 'error')}** — "
                    f"{body.get('message', 'Falha na consulta.')}"
                )
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err})
