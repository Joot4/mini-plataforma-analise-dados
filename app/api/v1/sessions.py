"""Session endpoints: schema manifest, conversation history, reset."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser
from app.schemas.sessions import ConversationTurnOut, SessionOut
from app.sessions.store import get_session_store

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error_type": "session_not_found",
            "message": "Sessão não encontrada ou expirada.",
        },
    )


@router.get(
    "/{session_id}",
    response_model=SessionOut,
    summary="Retorna o manifesto + histórico de conversa da sessão",
)
async def get_session(session_id: str, current_user: CurrentUser) -> SessionOut:
    store = get_session_store()
    record = store.get(session_id, str(current_user.id))
    if record is None:
        raise _not_found()
    return SessionOut(
        session_id=record.session_id,
        table_name=record.table_name,
        created_at=record.created_at.isoformat(),
        last_accessed_at=record.last_accessed_at.isoformat(),
        schema_manifest=record.schema.to_dict(),  # type: ignore[arg-type]
        history=[ConversationTurnOut(**t.to_dict()) for t in record.history],
    )


@router.delete(
    "/{session_id}/conversation",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Limpa o histórico de conversa (mantém o dataset)",
)
async def reset_conversation(session_id: str, current_user: CurrentUser) -> None:
    store = get_session_store()
    record = store.get(session_id, str(current_user.id))
    if record is None:
        raise _not_found()
    record.history.clear()
