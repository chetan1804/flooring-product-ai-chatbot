"""CLI for PostgreSQL schema setup and catalog ingestion."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from flooring_catalog.config import load_local_environment
from flooring_catalog.database import DatabaseSettings, apply_schema, database_connection
from flooring_catalog.ingestion import ingest_catalog


def main(argv: Sequence[str] | None = None) -> int:
    load_local_environment()
    parser = argparse.ArgumentParser(description="Ingest eligible flooring products")
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--apply-schema", action="store_true")
    parser.add_argument("--batch-size", type=int)
    args = parser.parse_args(argv)

    settings = DatabaseSettings.from_env()
    batch_size = args.batch_size or settings.ingest_batch_size
    with database_connection(settings) as connection:
        if args.apply_schema:
            apply_schema(connection)
        stats = ingest_catalog(connection, args.catalog, batch_size=batch_size)
    print(json.dumps(asdict(stats) | {"rejected_records": stats.rejected_records}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
