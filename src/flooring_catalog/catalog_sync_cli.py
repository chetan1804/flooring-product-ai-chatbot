"""Scheduled catalog synchronization command."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from flooring_catalog.catalog_sync import synchronize_catalog
from flooring_catalog.config import load_local_environment
from flooring_catalog.database import DatabaseSettings, apply_schema, database_connection
from flooring_catalog.embeddings import EmbeddingSettings, OpenAIEmbeddingProvider


def main(argv: Sequence[str] | None = None) -> int:
    load_local_environment()
    parser = argparse.ArgumentParser(
        description="Ingest a catalog snapshot and refresh stale embeddings"
    )
    parser.add_argument("catalog", type=Path)
    parser.add_argument(
        "--authoritative-snapshot",
        action="store_true",
        help="Deactivate searchable products absent or ineligible in this complete snapshot",
    )
    parser.add_argument("--batch-size", type=int)
    args = parser.parse_args(argv)

    database = DatabaseSettings.from_env()
    embeddings = EmbeddingSettings.from_env()
    provider = OpenAIEmbeddingProvider(embeddings)
    with database_connection(database) as connection:
        apply_schema(connection)
        stats = synchronize_catalog(
            connection,
            args.catalog,
            provider,
            batch_size=args.batch_size or database.ingest_batch_size,
            embedding_batch_size=embeddings.batch_size,
            max_text_characters=embeddings.max_text_characters,
            authoritative_snapshot=args.authoritative_snapshot,
        )
    print(json.dumps(asdict(stats), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
