"""Bounded development sessions and durable PostgreSQL production sessions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Protocol
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


@dataclass(frozen=True, slots=True)
class SessionRecord:
    session_id: UUID
    site_code: str
    created_at: datetime
    expires_at: datetime


class SessionStore(Protocol):
    def create(self, site_code: str) -> SessionRecord:
        """Create a server-owned session."""

    def get(self, session_id: UUID) -> SessionRecord | None:
        """Return and refresh a live session, or None when absent/expired."""


class InMemorySessionStore:
    """Thread-safe bounded store intended for tests and local development."""

    def __init__(
        self,
        *,
        ttl_seconds: int = 86_400,
        max_sessions: int = 10_000,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_sessions <= 0:
            raise ValueError("max_sessions must be positive")
        self._ttl = timedelta(seconds=ttl_seconds)
        self._max_sessions = max_sessions
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sessions: dict[UUID, SessionRecord] = {}
        self._last_accessed: dict[UUID, datetime] = {}
        self._lock = Lock()

    def create(self, site_code: str) -> SessionRecord:
        now = self._clock()
        record = SessionRecord(
            session_id=uuid4(),
            site_code=site_code,
            created_at=now,
            expires_at=now + self._ttl,
        )
        with self._lock:
            self._prune(now)
            if len(self._sessions) >= self._max_sessions:
                oldest = min(self._last_accessed, key=self._last_accessed.__getitem__)
                self._sessions.pop(oldest, None)
                self._last_accessed.pop(oldest, None)
            self._sessions[record.session_id] = record
            self._last_accessed[record.session_id] = now
        return record

    def get(self, session_id: UUID) -> SessionRecord | None:
        now = self._clock()
        with self._lock:
            self._prune(now)
            record = self._sessions.get(session_id)
            if record is None:
                return None
            refreshed = SessionRecord(
                session_id=record.session_id,
                site_code=record.site_code,
                created_at=record.created_at,
                expires_at=now + self._ttl,
            )
            self._sessions[session_id] = refreshed
            self._last_accessed[session_id] = now
            return refreshed

    def _prune(self, now: datetime) -> None:
        expired = [
            session_id
            for session_id, record in self._sessions.items()
            if record.expires_at <= now
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)
            self._last_accessed.pop(session_id, None)


class PostgresSessionStore:
    """Shared sliding-expiration sessions suitable for multiple API replicas."""

    def __init__(self, pool: ConnectionPool, *, ttl_seconds: int = 86_400) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._pool = pool
        self._ttl_seconds = ttl_seconds

    def create(self, site_code: str) -> SessionRecord:
        session_id = uuid4()
        with (
            self._pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute("DELETE FROM chatbot_sessions WHERE expires_at <= now()")
            cursor.execute(
                """
INSERT INTO chatbot_sessions (session_id, site_code, expires_at)
VALUES (%(session_id)s, %(site_code)s, now() + make_interval(secs => %(ttl)s))
RETURNING session_id, site_code, created_at, expires_at
""",
                {
                    "session_id": session_id,
                    "site_code": site_code,
                    "ttl": self._ttl_seconds,
                },
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("database did not return the created session")
        return SessionRecord(**row)

    def get(self, session_id: UUID) -> SessionRecord | None:
        with (
            self._pool.connection() as connection,
            connection.cursor(row_factory=dict_row) as cursor,
        ):
            cursor.execute(
                """
UPDATE chatbot_sessions
SET last_accessed_at = now(),
    expires_at = now() + make_interval(secs => %(ttl)s)
WHERE session_id = %(session_id)s
  AND expires_at > now()
RETURNING session_id, site_code, created_at, expires_at
""",
                {"session_id": session_id, "ttl": self._ttl_seconds},
            )
            row = cursor.fetchone()
        return SessionRecord(**row) if row is not None else None
