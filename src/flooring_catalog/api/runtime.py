"""Production dependency wiring owned by the FastAPI lifespan."""

from __future__ import annotations

from dataclasses import dataclass

from psycopg_pool import ConnectionPool

from flooring_catalog.agent import FlooringConversationAgent, build_flooring_agent_graph
from flooring_catalog.database import DatabaseSettings
from flooring_catalog.embeddings import EmbeddingSettings, OpenAIEmbeddingProvider
from flooring_catalog.recommendations import ClientDomainSettings, RecommendationCardService
from flooring_catalog.requirements import (
    OpenAIRequirementExtractor,
    RequirementExtractionService,
    RequirementExtractionSettings,
)
from flooring_catalog.requirements.vocabulary import CatalogVocabularyRepository
from flooring_catalog.search import HybridSearchService, ProductSearchRepository, SearchFilters
from flooring_catalog.search.models import HybridCandidate


class PooledCandidateSearchService:
    """Acquire a short-lived database connection for each search operation."""

    def __init__(
        self,
        pool: ConnectionPool,
        embedding_provider: OpenAIEmbeddingProvider,
    ) -> None:
        self._pool = pool
        self._embedding_provider = embedding_provider

    def search(self, *, query: str | None, filters: SearchFilters) -> list[HybridCandidate]:
        with self._pool.connection() as connection:
            service = HybridSearchService(
                ProductSearchRepository(connection),
                self._embedding_provider,
            )
            return service.search(query=query, filters=filters)


@dataclass(slots=True)
class RuntimeResources:
    agent: FlooringConversationAgent
    pool: ConnectionPool

    def close(self) -> None:
        self.pool.close()


def build_runtime_resources() -> RuntimeResources:
    """Build expensive shared resources once during application startup."""

    database_settings = DatabaseSettings.from_env()
    extraction_settings = RequirementExtractionSettings.from_env()
    embedding_settings = EmbeddingSettings.from_env()
    client_settings = ClientDomainSettings.from_env()

    pool = ConnectionPool(
        conninfo=database_settings.database_url,
        min_size=1,
        max_size=10,
        open=False,
    )
    try:
        pool.open(wait=True)
        with pool.connection() as connection:
            vocabulary = CatalogVocabularyRepository(connection).load()
        extractor = OpenAIRequirementExtractor(extraction_settings)
        extraction_service = RequirementExtractionService(extractor, vocabulary)
        embedding_provider = OpenAIEmbeddingProvider(embedding_settings)
        search_service = PooledCandidateSearchService(pool, embedding_provider)
        graph = build_flooring_agent_graph(
            extraction_service,
            search_service,
            vocabulary.product_types,
            recommendation_service=RecommendationCardService(client_settings.client_domain),
        )
        return RuntimeResources(agent=FlooringConversationAgent(graph), pool=pool)
    except Exception:
        pool.close()
        raise
