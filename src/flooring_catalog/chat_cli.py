"""Interactive development CLI for the LangGraph flooring conversation agent."""

from __future__ import annotations

import argparse
import uuid

from flooring_catalog.agent import FlooringConversationAgent, build_flooring_agent_graph
from flooring_catalog.config import load_local_environment
from flooring_catalog.database import DatabaseSettings, database_connection
from flooring_catalog.embeddings import EmbeddingSettings, OpenAIEmbeddingProvider
from flooring_catalog.requirements import (
    OpenAIRequirementExtractor,
    RequirementExtractionService,
    RequirementExtractionSettings,
)
from flooring_catalog.requirements.vocabulary import CatalogVocabularyRepository
from flooring_catalog.search import HybridSearchService, ProductSearchRepository


def main() -> int:
    load_local_environment()
    parser = argparse.ArgumentParser(description="Run an interactive flooring conversation")
    parser.add_argument("--thread-id", default=str(uuid.uuid4()))
    args = parser.parse_args()

    database_settings = DatabaseSettings.from_env()
    extraction_settings = RequirementExtractionSettings.from_env()
    embedding_settings = EmbeddingSettings.from_env()
    extractor = OpenAIRequirementExtractor(extraction_settings)
    embedding_provider = OpenAIEmbeddingProvider(embedding_settings)

    with database_connection(database_settings) as connection:
        vocabulary = CatalogVocabularyRepository(connection).load()
        extraction_service = RequirementExtractionService(extractor, vocabulary)
        search_service = HybridSearchService(
            ProductSearchRepository(connection), embedding_provider
        )
        graph = build_flooring_agent_graph(
            extraction_service,
            search_service,
            vocabulary.product_types,
        )
        agent = FlooringConversationAgent(graph)

        print(f"Conversation thread: {args.thread_id}")
        print("Enter 'quit' to stop.")
        while True:
            try:
                message = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if message.casefold() in {"quit", "exit"}:
                break
            if not message:
                continue
            result = agent.respond(thread_id=args.thread_id, user_message=message)
            print(f"Assistant: {result.message}")
            if result.candidate_skus:
                print(f"Candidate SKUs: {', '.join(result.candidate_skus)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

