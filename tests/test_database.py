from __future__ import annotations

import pytest

from flooring_catalog.database.connection import DatabaseSettings
from flooring_catalog.database.schema import migration_sql


def test_database_settings_are_loaded_from_environment_mapping() -> None:
    settings = DatabaseSettings.from_env(
        {"DATABASE_URL": "postgresql://localhost/catalog", "INGEST_BATCH_SIZE": "250"}
    )
    assert settings.database_url == "postgresql://localhost/catalog"
    assert settings.ingest_batch_size == 250


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({}, "DATABASE_URL is required"),
        ({"DATABASE_URL": "postgresql://x", "INGEST_BATCH_SIZE": "abc"}, "must be an integer"),
        ({"DATABASE_URL": "postgresql://x", "INGEST_BATCH_SIZE": "0"}, "must be positive"),
    ],
)
def test_invalid_database_settings_are_rejected(
    environment: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        DatabaseSettings.from_env(environment)


def test_migration_prepares_pgvector_jsonb_constraints_and_indexes() -> None:
    sql = migration_sql()
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "metadata JSONB NOT NULL" in sql
    assert "CHECK (lower(btrim(status)) = 'active')" in sql
    assert "CHECK (btrim(swatch) <> '')" in sql
    assert "USING GIN (metadata)" in sql
    assert "WHERE price IS NOT NULL" in sql

