"""Thread-safe in-memory task registry for upload/processing jobs.

Baseline for Phase 2 (OPS-01). Phase 3 may swap this for a Redis-backed store if
multi-worker horizontal scale is needed — the interface here is deliberately small.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


@dataclass
class TaskRecord:
    task_id: str
    user_id: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    progress: float = 0.0  # 0.0 – 1.0
    result: dict[str, Any] | None = None
    error: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "progress": round(self.progress, 3),
            "result": self.result,
            "error": self.error,
        }


class TaskRegistry:
    """Thread-safe dict-backed task registry.

    Intentionally minimal: `create`, `get`, `update`. No automatic GC — the Phase 3
    session TTL sweeper will piggyback on this once sessions are introduced.
    """

    def __init__(self) -> None:
        self._store: dict[str, TaskRecord] = {}
        self._lock = threading.Lock()

    def create(self, user_id: str) -> TaskRecord:
        task_id = str(uuid.uuid4())
        record = TaskRecord(task_id=task_id, user_id=user_id)
        with self._lock:
            self._store[task_id] = record
        return record

    def get(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            return self._store.get(task_id)

    def update(
        self,
        task_id: str,
        *,
        status: TaskStatus | None = None,
        progress: float | None = None,
        result: dict[str, Any] | None = None,
        error: dict[str, str] | None = None,
    ) -> TaskRecord | None:
        with self._lock:
            record = self._store.get(task_id)
            if record is None:
                return None
            if status is not None:
                record.status = status
            if progress is not None:
                record.progress = progress
            if result is not None:
                record.result = result
            if error is not None:
                record.error = error
            record.updated_at = datetime.now(tz=timezone.utc)
            return record

    def owned_by(self, task_id: str, user_id: str) -> TaskRecord | None:
        """Return the task only if `user_id` owns it. Enforces cross-user isolation."""
        record = self.get(task_id)
        if record is None or record.user_id != user_id:
            return None
        return record


_registry_singleton: TaskRegistry | None = None
_singleton_lock = threading.Lock()


def get_task_registry() -> TaskRegistry:
    """FastAPI dependency / module-level accessor. One registry per process."""
    global _registry_singleton
    if _registry_singleton is None:
        with _singleton_lock:
            if _registry_singleton is None:
                _registry_singleton = TaskRegistry()
    return _registry_singleton


def reset_task_registry() -> None:
    """Test-only: clear the singleton so each test gets a fresh registry."""
    global _registry_singleton
    with _singleton_lock:
        _registry_singleton = None


__all__ = [
    "TaskStatus",
    "TaskRecord",
    "TaskRegistry",
    "get_task_registry",
    "reset_task_registry",
]
