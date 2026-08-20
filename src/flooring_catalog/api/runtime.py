"""Production dependency wiring owned by the FastAPI lifespan."""

from __future__ import annotations

from dataclasses import dataclass

from langgraph.checkpoint.postgres import PostgresSaver
from openai import OpenAI
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from flooring_catalog.agent import FlooringConversationAgent, build_flooring_agent_graph
from flooring_catalog.analytics import PostgresAnalyticsStore
from flooring_catalog.api.sessions import PostgresSessionStore
from flooring_catalog.database import DatabaseSettings
from flooring_catalog.embeddings import EmbeddingSettings, OpenAIEmbeddingProvider
from flooring_catalog.production import ProductionSettings
from flooring_catalog.recommendations import RecommendationCardService
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
    sessions: PostgresSessionStore
    analytics: PostgresAnalyticsStore

    def ready(self) -> bool:
        with self.pool.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
SELECT to_regclass('public.catalog_products') IS NOT NULL
   AND to_regclass('public.chatbot_sessions') IS NOT NULL
   AND to_regclass('public.checkpoints') IS NOT NULL
   AND to_regclass('public.analytics_events') IS NOT NULL
   AND to_regclass('public.recommendation_feedback') IS NOT NULL AS ready
"""
            )
            row = cursor.fetchone()
        return bool(row and row["ready"])

    def close(self) -> None:
        self.pool.close()


def build_runtime_resources(settings: ProductionSettings) -> RuntimeResources:
    """Build expensive shared resources once during application startup."""

    database_settings = DatabaseSettings.from_env()
    extraction_settings = RequirementExtractionSettings.from_env()
    embedding_settings = EmbeddingSettings.from_env()

    pool = ConnectionPool(
        conninfo=database_settings.database_url,
        min_size=settings.database_pool_min_size,
        max_size=settings.database_pool_max_size,
        timeout=settings.database_pool_timeout_seconds,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        open=False,
    )
    try:
        pool.open(wait=True, timeout=settings.database_pool_timeout_seconds)
        with pool.connection() as connection:
            vocabulary = CatalogVocabularyRepository(connection).load()
        openai_client = OpenAI(
            timeout=settings.openai_timeout_seconds,
            max_retries=settings.openai_max_retries,
        )
        extractor = OpenAIRequirementExtractor(extraction_settings, client=openai_client)
        extraction_service = RequirementExtractionService(extractor, vocabulary)
        embedding_provider = OpenAIEmbeddingProvider(
            embedding_settings,
            client=openai_client,
        )
        search_service = PooledCandidateSearchService(pool, embedding_provider)
        checkpointer = PostgresSaver(pool)
        graph = build_flooring_agent_graph(
            extraction_service,
            search_service,
            vocabulary.product_types,
            recommendation_service=RecommendationCardService(),
            checkpointer=checkpointer,
        )
        sessions = PostgresSessionStore(
            pool,
            ttl_seconds=settings.session_ttl_seconds,
        )
        analytics = PostgresAnalyticsStore(pool)
        return RuntimeResources(
            agent=FlooringConversationAgent(graph),
            pool=pool,
            sessions=sessions,
            analytics=analytics,
        )
    except Exception:
        pool.close()
        raise
