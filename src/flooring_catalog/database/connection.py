"""Environment-based PostgreSQL configuration and safe connection ownership."""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass

import psycopg
from psycopg import Connection


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    """Database settings loaded at the application boundary."""

    database_url: str
    ingest_batch_size: int = 1000

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> DatabaseSettings:
        values = os.environ if environ is None else environ
        database_url = values.get("DATABASE_URL", "").strip()
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        try:
            batch_size = int(values.get("INGEST_BATCH_SIZE", "1000"))
        except ValueError as error:
            raise ValueError("INGEST_BATCH_SIZE must be an integer") from error
        if batch_size <= 0:
            raise ValueError("INGEST_BATCH_SIZE must be positive")
        return cls(database_url=database_url, ingest_batch_size=batch_size)


@contextmanager
def database_connection(settings: DatabaseSettings) -> Iterator[Connection]:
    """Open and always close a caller-owned PostgreSQL connection."""

    with psycopg.connect(settings.database_url) as connection:
        yield connection

