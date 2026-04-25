"""Background asyncio task that periodically sweeps expired sessions."""

from __future__ import annotations

import asyncio

from app.core.logging import get_logger
from app.sessions.store import SessionStore

logger = get_logger("app.sessions.sweeper")

DEFAULT_INTERVAL_SECONDS = 300  # 5 minutes — matches AUTH-06


async def run_sweeper(
    store: SessionStore,
    *,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
) -> None:
    """Periodic task: on every tick, drop expired sessions from `store`.

    Cancellable — the lifespan context cancels this task on shutdown.
    """
    logger.info("sweeper.started", interval_seconds=interval_seconds)
    try:
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                store.sweep()
            except Exception as exc:
                logger.error("sweeper.error", exc_info=exc)
    except asyncio.CancelledError:
        logger.info("sweeper.stopped")
        raise
