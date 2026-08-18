"""CLI for manual structured and semantic retrieval checks."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from decimal import Decimal

from flooring_catalog.database import DatabaseSettings, database_connection
from flooring_catalog.embeddings import EmbeddingSettings, OpenAIEmbeddingProvider
from flooring_catalog.search import (
    HybridSearchConfig,
    HybridSearchService,
    ProductSearchRepository,
    SearchFilters,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run hybrid flooring product retrieval")
    parser.add_argument("--query")
    parser.add_argument("--type", action="append", default=[])
    parser.add_argument("--brand", action="append", default=[])
    parser.add_argument("--material", action="append", default=[])
    parser.add_argument("--color", action="append", default=[])
    parser.add_argument("--style", action="append", default=[])
    parser.add_argument("--minimum-price", type=Decimal)
    parser.add_argument("--maximum-price", type=Decimal)
    parser.add_argument("--waterproof", choices=("yes", "no"))
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    filters = SearchFilters(
        z_prod_types=tuple(args.type),
        brands=tuple(args.brand),
        materials=tuple(args.material),
        colors=tuple(args.color),
        styles=tuple(args.style),
        minimum_price=args.minimum_price,
        maximum_price=args.maximum_price,
        waterproof=(args.waterproof == "yes" if args.waterproof else None),
    )
    database_settings = DatabaseSettings.from_env()
    provider = OpenAIEmbeddingProvider(EmbeddingSettings.from_env()) if args.query else None
    with database_connection(database_settings) as connection:
        service = HybridSearchService(
            ProductSearchRepository(connection),
            provider,
            HybridSearchConfig(result_limit=args.limit, candidate_limit=max(50, args.limit)),
        )
        candidates = service.search(query=args.query, filters=filters)
    print(json.dumps([asdict(candidate) for candidate in candidates], indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
