from __future__ import annotations

from pydantic import BaseModel, Field


class FieldError(BaseModel):
    """Per-field validation error inside ErrorResponse.details.fields[]."""

    field: str
    msg: str


class ErrorDetails(BaseModel):
    """Optional structured details payload for ErrorResponse."""

    fields: list[FieldError] | None = None


class ErrorResponse(BaseModel):
    """Standard error envelope (CONTEXT.md D-01..D-04).

    - error_type: stable machine-readable snake_case English (contract)
    - message: PT-BR user-friendly text
    - details: optional structured info (e.g., per-field validation errors)
    """

    error_type: str = Field(..., examples=["invalid_credentials"])
    message: str = Field(..., examples=["Email ou senha inválidos."])
    details: ErrorDetails | None = None


__all__ = ["ErrorResponse", "ErrorDetails", "FieldError"]
