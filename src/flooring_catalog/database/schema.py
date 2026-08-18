"""Schema migration execution."""

from __future__ import annotations

from importlib.resources import files

from psycopg import Connection


def migration_sql() -> str:
    """Load all bundled idempotent migrations in filename order."""

    migrations = files("flooring_catalog.database.migrations")
    sql_files = sorted(
        (resource for resource in migrations.iterdir() if resource.name.endswith(".sql")),
        key=lambda resource: resource.name,
    )
    return "\n\n".join(resource.read_text(encoding="utf-8") for resource in sql_files)


def apply_schema(connection: Connection) -> None:
    """Apply the idempotent schema migration in one transaction."""

    try:
        with connection.cursor() as cursor:
            cursor.execute(migration_sql())
        connection.commit()
    except Exception:
        connection.rollback()
        raise
