from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", summary="Readiness probe")
async def health() -> dict[str, str]:
    """Container/load-balancer readiness probe. Always 200 if process is up."""
    return {"status": "ok"}
