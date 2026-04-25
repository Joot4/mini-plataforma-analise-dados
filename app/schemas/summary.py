from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NarrationResponse(BaseModel):
    """Structured-output schema the LLM is instructed to conform to.

    Keep this minimal: a single 2-3 paragraph PT-BR text field. `parse()` with
    this schema prevents the LLM from returning HTML/markdown wrappers.
    """

    narration: str = Field(
        ...,
        description="Narração em português (PT-BR) do dataset, 2 a 3 parágrafos.",
    )


class SummaryOut(BaseModel):
    """Summary shape returned inside the upload task result."""

    rows: int
    cols: int
    columns: list[dict[str, Any]]
    narration: str | None = None
    narration_error: str | None = None
