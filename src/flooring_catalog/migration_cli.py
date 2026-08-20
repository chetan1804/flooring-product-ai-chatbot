"""Apply application and LangGraph checkpoint migrations as a deployment task."""

from __future__ import annotations

from langgraph.checkpoint.postgres import PostgresSaver

from flooring_catalog.config import load_local_environment
from flooring_catalog.database import DatabaseSettings, apply_schema, database_connection


def main() -> int:
    load_local_environment()
    settings = DatabaseSettings.from_env()
    with database_connection(settings) as connection:
        apply_schema(connection)
    # LangGraph owns and versions its checkpoint tables through setup().
    with PostgresSaver.from_conn_string(settings.database_url) as checkpointer:
        checkpointer.setup()
    print("Application and LangGraph database migrations applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
