"""Manual CLI for AI customer requirement extraction."""

from __future__ import annotations

import argparse
import json

from flooring_catalog.database import DatabaseSettings, database_connection
from flooring_catalog.requirements import (
    OpenAIRequirementExtractor,
    RequirementExtractionService,
    RequirementExtractionSettings,
)
from flooring_catalog.requirements.models import serializable_result
from flooring_catalog.requirements.vocabulary import CatalogVocabularyRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract flooring customer requirements")
    parser.add_argument("message", help="One customer message to analyze")
    args = parser.parse_args()

    database_settings = DatabaseSettings.from_env()
    extraction_settings = RequirementExtractionSettings.from_env()
    with database_connection(database_settings) as connection:
        vocabulary = CatalogVocabularyRepository(connection).load()
    extractor = OpenAIRequirementExtractor(extraction_settings)
    result = RequirementExtractionService(extractor, vocabulary).extract(args.message)
    print(json.dumps(serializable_result(result), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

