"""Schema migration execution."""

from __future__ import annotations

from importlib.resources import files

from psycopg import Connection


def migration_sql() -> str:
    """Load the versioned Step 2 migration bundled with the package."""

    migration = files("flooring_catalog.database.migrations").joinpath(
        "001_create_catalog_products.sql"
    )
    return migration.read_text(encoding="utf-8")


def apply_schema(connection: Connection) -> None:
    """Apply the idempotent schema migration in one transaction."""

    try:
        with connection.cursor() as cursor:
            cursor.execute(migration_sql())
        connection.commit()
    except Exception:
        connection.rollback()
        raise

