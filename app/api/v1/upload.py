"""POST /upload + GET /upload/{task_id}/status.

Upload flow:
1. Validate size upfront (header + stream cap) → 413 if too big.
2. Stream bytes to `/data/uploads/{user_id}/{task_id}{suffix}`.
3. Register a task in the in-memory registry.
4. Schedule background processing via FastAPI BackgroundTasks.
5. Return 202 with task_id immediately.

Background worker (runs via `loop.run_in_executor` to keep pandas/openpyxl off the
event loop) calls `ingest_file`, updates the task record, and removes the raw file
on success. On failure, the file is kept for debugging and the error is recorded.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.core.logging import get_logger
from app.ingestion.cleaning import CleaningOptions
from app.ingestion.reader import (
    EmptyFileError,
    SingleColumnError,
    UnsupportedFormatError,
)
from app.ingestion.service import ingest_file
from app.schemas.upload import TaskStatusResponse, UploadAcceptedResponse
from app.sessions.store import get_session_store
from app.tasks.registry import TaskStatus, get_task_registry

router = APIRouter(prefix="/upload", tags=["upload"])
logger = get_logger("app.upload")

ALLOWED_SUFFIXES = {".csv", ".tsv", ".xlsx"}

_TOO_LARGE = {
    "error_type": "file_too_large",
    "message": "Arquivo excede o limite de 50MB.",
}
_TOO_MANY_ROWS = {
    "error_type": "too_many_rows",
    "message": "Arquivo excede o limite de 500.000 linhas.",
}
_BAD_FORMAT = {
    "error_type": "unsupported_format",
    "message": "Formato não suportado. Envie .csv, .tsv ou .xlsx.",
}


def _uploads_dir_for(user_id: str) -> Path:
    settings = get_settings()
    base = Path(settings.UPLOADS_DIR)
    # If the configured UPLOADS_DIR isn't writable (e.g. /data/uploads inside a test
    # container), fall back to the repo-relative ./data/uploads that the project uses.
    if not base.parent.exists():
        base = Path("./data/uploads").resolve()
    user_dir = base / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


async def _stream_to_disk(
    upload: UploadFile, destination: Path, max_bytes: int
) -> int:
    """Write the upload to disk in chunks, raising 413 if the byte cap is exceeded."""
    total = 0
    chunk_size = 64 * 1024
    with destination.open("wb") as out:
        while True:
            chunk = await upload.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                destination.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=_TOO_LARGE)
            out.write(chunk)
    return total


def _run_ingest_job(
    task_id: str, user_id: str, file_path: Path, max_rows: int
) -> None:
    """Executed inside a thread pool by BackgroundTasks → loop.run_in_executor."""
    registry = get_task_registry()
    registry.update(task_id, status=TaskStatus.RUNNING, progress=0.1)
    try:
        result = ingest_file(file_path, options=CleaningOptions())
        if result.raw_row_count > max_rows:
            registry.update(
                task_id,
                status=TaskStatus.ERROR,
                progress=1.0,
                error=_TOO_MANY_ROWS,
            )
            return
        # Materialize into an isolated DuckDB session.
        store = get_session_store()
        session = store.create(user_id=user_id, df=result.df, schema=result.schema)
        response = result.to_response()
        response["session_id"] = session.session_id
        registry.update(
            task_id,
            status=TaskStatus.DONE,
            progress=1.0,
            result=response,
        )
        file_path.unlink(missing_ok=True)
    except (UnsupportedFormatError, SingleColumnError, EmptyFileError) as exc:
        registry.update(
            task_id,
            status=TaskStatus.ERROR,
            progress=1.0,
            error={"error_type": "ingestion_failed", "message": str(exc)},
        )
    except Exception as exc:
        logger.error("ingest.unhandled", exc_info=exc, task_id=task_id)
        registry.update(
            task_id,
            status=TaskStatus.ERROR,
            progress=1.0,
            error={
                "error_type": "internal_error",
                "message": "Falha inesperada no processamento.",
            },
        )


async def _run_ingest_async(
    task_id: str, user_id: str, file_path: Path, max_rows: int
) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None, _run_ingest_job, task_id, user_id, file_path, max_rows
    )


@router.post(
    "",
    response_model=UploadAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enviar arquivo para processamento",
)
async def upload_file(
    current_user: CurrentUser,
    background: BackgroundTasks,
    file: UploadFile = File(...),
) -> UploadAcceptedResponse:
    settings = get_settings()

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail=_BAD_FORMAT)

    registry = get_task_registry()
    task = registry.create(user_id=str(current_user.id))

    user_dir = _uploads_dir_for(str(current_user.id))
    destination = user_dir / f"{task.task_id}{suffix}"

    size = await _stream_to_disk(file, destination, settings.MAX_UPLOAD_BYTES)
    logger.info(
        "upload.accepted",
        task_id=task.task_id,
        user_id=str(current_user.id),
        bytes=size,
        filename=file.filename,
    )

    background.add_task(
        _run_ingest_async,
        task.task_id,
        str(current_user.id),
        destination,
        settings.MAX_UPLOAD_ROWS,
    )

    return UploadAcceptedResponse(task_id=task.task_id)


@router.get(
    "/{task_id}/status",
    response_model=TaskStatusResponse,
    summary="Consultar status do processamento",
)
async def get_upload_status(task_id: str, current_user: CurrentUser) -> TaskStatusResponse:
    registry = get_task_registry()
    record = registry.owned_by(task_id, str(current_user.id))
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_type": "task_not_found",
                "message": "Tarefa não encontrada.",
            },
        )
    return TaskStatusResponse(**record.to_dict())
