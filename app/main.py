from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1 import auth as auth_router
from app.api.v1 import health as health_router
from app.api.v1 import upload as upload_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.schemas.errors import ErrorDetails, ErrorResponse, FieldError


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.LOG_LEVEL, debug=settings.DEBUG)
    logger = get_logger("app.lifespan")
    logger.info("app.startup", debug=settings.DEBUG, log_level=settings.LOG_LEVEL)
    yield
    logger.info("app.shutdown")


def _envelope(error_type: str, message: str, details: ErrorDetails | None = None) -> dict[str, Any]:
    return ErrorResponse(error_type=error_type, message=message, details=details).model_dump(
        exclude_none=True
    )


async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "error_type" in exc.detail and "message" in exc.detail:
        body = _envelope(
            error_type=str(exc.detail["error_type"]),
            message=str(exc.detail["message"]),
            details=ErrorDetails(**exc.detail["details"])
            if exc.detail.get("details")
            else None,
        )
    else:
        body = _envelope(error_type="http_error", message=str(exc.detail))
    return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)


async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    fields = [
        FieldError(
            field=".".join(str(p) for p in err.get("loc", []) if p not in ("body",)),
            msg=str(err.get("msg", "")),
        )
        for err in exc.errors()
    ]
    body = _envelope(
        error_type="validation_failed",
        message="Os dados enviados são inválidos.",
        details=ErrorDetails(fields=fields),
    )
    return JSONResponse(status_code=422, content=body)


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    settings = get_settings()
    get_logger("app.unhandled").error(
        "unhandled_exception", exc_info=exc, path=str(request.url.path)
    )
    body: dict[str, Any] = _envelope(
        error_type="internal_error",
        message="Ocorreu um erro interno. Tente novamente mais tarde.",
    )
    if settings.DEBUG:
        body["details"] = {"exception": repr(exc)}
    return JSONResponse(status_code=500, content=body)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Mini Plataforma de Análise de Dados",
        description="API-only PT-BR data analysis backend.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_exception_handler(HTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)

    app.include_router(health_router.router, prefix="/api/v1")
    app.include_router(auth_router.router, prefix="/api/v1")
    app.include_router(upload_router.router, prefix="/api/v1")

    return app


app = create_app()
