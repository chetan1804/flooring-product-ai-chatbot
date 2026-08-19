"""CLI for generating catalog product embeddings."""

from __future__ import annotations

import json
from dataclasses import asdict

from flooring_catalog.config import load_local_environment
from flooring_catalog.database import DatabaseSettings, database_connection
from flooring_catalog.embeddings import (
    EmbeddingSettings,
    OpenAIEmbeddingProvider,
    update_product_embeddings,
)


def main() -> int:
    load_local_environment()
    database_settings = DatabaseSettings.from_env()
    embedding_settings = EmbeddingSettings.from_env()
    provider = OpenAIEmbeddingProvider(embedding_settings)
    with database_connection(database_settings) as connection:
        stats = update_product_embeddings(
            connection,
            provider,
            batch_size=embedding_settings.batch_size,
            max_text_characters=embedding_settings.max_text_characters,
        )
    print(json.dumps(asdict(stats), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
