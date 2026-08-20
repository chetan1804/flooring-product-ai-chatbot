from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from flooring_catalog.api.sessions import PostgresSessionStore


class FakeCursor:
    def __init__(self) -> None:
        self.executions: list[tuple[str, dict[str, Any]]] = []
        self.row: dict[str, Any] | None = None

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str, parameters: dict[str, Any] | None = None) -> None:
        values = parameters or {}
        self.executions.append((statement, values))
        if "RETURNING" not in statement:
            self.row = None
            return
        now = datetime(2026, 1, 1, tzinfo=UTC)
        self.row = {
            "session_id": values["session_id"],
            "site_code": values.get("site_code", "CLIENT001"),
            "created_at": now,
            "expires_at": now + timedelta(seconds=values["ttl"]),
        }

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self, **_kwargs: object) -> FakeCursor:
        return self._cursor


class FakePool:
    def __init__(self) -> None:
        self.cursor = FakeCursor()
        self.connection_value = FakeConnection(self.cursor)

    def connection(self):  # type: ignore[no-untyped-def]
        return nullcontext(self.connection_value)


def test_postgres_session_store_uses_bound_values_and_sliding_expiration() -> None:
    pool = FakePool()
    store = PostgresSessionStore(pool, ttl_seconds=300)  # type: ignore[arg-type]
    created = store.create("CLIENT001")
    assert created.site_code == "CLIENT001"
    insert_statement, insert_values = pool.cursor.executions[1]
    assert "%(site_code)s" in insert_statement
    assert insert_values["site_code"] == "CLIENT001"
    assert insert_values["ttl"] == 300

    session_id = UUID("85d60cba-e03a-4f34-b285-ff4841e004f7")
    fetched = store.get(session_id)
    assert fetched is not None
    update_statement, update_values = pool.cursor.executions[-1]
    assert "expires_at = now() + make_interval" in update_statement
    assert update_values == {"session_id": session_id, "ttl": 300}
