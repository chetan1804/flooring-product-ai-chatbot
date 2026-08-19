"""Thread-safe in-process session registry for the initial hosted API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class SessionRecord:
    session_id: UUID
    site_code: str
    created_at: datetime


class InMemorySessionStore:
    """Own session identifiers without accepting caller-selected LangGraph thread IDs."""

    def __init__(self) -> None:
        self._sessions: dict[UUID, SessionRecord] = {}
        self._lock = Lock()

    def create(self, site_code: str) -> SessionRecord:
        record = SessionRecord(
            session_id=uuid4(),
            site_code=site_code,
            created_at=datetime.now(UTC),
        )
        with self._lock:
            self._sessions[record.session_id] = record
        return record

    def get(self, session_id: UUID) -> SessionRecord | None:
        with self._lock:
            return self._sessions.get(session_id)
