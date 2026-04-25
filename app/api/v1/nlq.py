"""POST /sessions/{session_id}/query — the core NL-to-insight endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.nlq.service import NLQError, answer_question
from app.schemas.nlq import QueryRequest, QueryResponse
from app.sessions.store import get_session_store

router = APIRouter(prefix="/sessions", tags=["nlq"])


@router.post(
    "/{session_id}/query",
    response_model=QueryResponse,
    summary="Pergunta em linguagem natural sobre a sessão",
)
async def query_session(
    session_id: str, payload: QueryRequest, current_user: CurrentUser
) -> QueryResponse:
    store = get_session_store()
    session = store.get(session_id, str(current_user.id))
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_type": "session_not_found",
                "message": "Sessão não encontrada ou expirada.",
            },
        )

    settings = get_settings()
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail={
                "error_type": "llm_unavailable",
                "message": (
                    "Este endpoint requer OPENAI_API_KEY configurada. "
                    "Configure a chave e tente novamente."
                ),
            },
        )

    try:
        return await answer_question(session, payload.question)
    except NLQError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error_type": exc.error_type, "message": exc.message},
        ) from exc
