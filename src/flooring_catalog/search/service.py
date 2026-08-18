"""Hybrid candidate retrieval without later-stage flooring business ranking."""

from __future__ import annotations

from dataclasses import dataclass

from flooring_catalog.embeddings import EmbeddingProvider
from flooring_catalog.search.models import HybridCandidate, SearchFilters, SearchProduct
from flooring_catalog.search.repository import ProductSearchRepository


@dataclass(frozen=True, slots=True)
class HybridSearchConfig:
    candidate_limit: int = 50
    result_limit: int = 20
    structured_weight: float = 0.4
    semantic_weight: float = 0.6

    def __post_init__(self) -> None:
        if self.candidate_limit <= 0:
            raise ValueError("candidate_limit must be positive")
        if self.candidate_limit > 200:
            raise ValueError("candidate_limit cannot exceed 200")
        if not 1 <= self.result_limit <= self.candidate_limit:
            raise ValueError("result_limit must be between 1 and candidate_limit")
        if self.structured_weight < 0 or self.semantic_weight < 0:
            raise ValueError("retrieval weights cannot be negative")
        if self.structured_weight + self.semantic_weight == 0:
            raise ValueError("at least one retrieval weight must be positive")


class HybridSearchService:
    """Union exact-filter and semantic candidates with transparent retrieval scores."""

    def __init__(
        self,
        repository: ProductSearchRepository,
        embedding_provider: EmbeddingProvider | None,
        config: HybridSearchConfig | None = None,
    ) -> None:
        self._repository = repository
        self._embedding_provider = embedding_provider
        self._config = config or HybridSearchConfig()

    def search(self, *, query: str | None, filters: SearchFilters) -> list[HybridCandidate]:
        normalized_query = query.strip() if query else ""
        if not normalized_query and not filters.active:
            raise ValueError("a semantic query or at least one structured filter is required")

        products: dict[str, SearchProduct] = {}
        structured_skus: set[str] = set()
        similarities: dict[str, float] = {}

        if filters.active:
            structured = self._repository.structured_search(
                filters, limit=self._config.candidate_limit
            )
            products.update((product.sku, product) for product in structured)
            structured_skus.update(product.sku for product in structured)

        if normalized_query:
            if self._embedding_provider is None:
                raise ValueError("an embedding provider is required for semantic search")
            query_vectors = self._embedding_provider.embed([normalized_query])
            if len(query_vectors) != 1:
                raise ValueError("embedding provider did not return one query vector")
            semantic = self._repository.semantic_search(
                query_vectors[0],
                self._embedding_provider.model,
                filters,
                limit=self._config.candidate_limit,
            )
            for product in semantic:
                products[product.sku] = product
                if filters.active:
                    structured_skus.add(product.sku)
                similarity = product.semantic_similarity
                if similarity is not None:
                    similarities[product.sku] = max(0.0, min(1.0, similarity))

        candidates = [
            self._candidate(
                product,
                product.sku in structured_skus,
                similarities.get(product.sku),
                structured_enabled=filters.active,
                semantic_enabled=bool(normalized_query),
            )
            for product in products.values()
        ]
        candidates.sort(
            key=lambda candidate: (
                -candidate.retrieval_score,
                -(candidate.semantic_similarity or 0.0),
                candidate.product.sku,
            )
        )
        return candidates[: self._config.result_limit]

    def _candidate(
        self,
        product: SearchProduct,
        structured_match: bool,
        semantic_similarity: float | None,
        *,
        structured_enabled: bool,
        semantic_enabled: bool,
    ) -> HybridCandidate:
        structured_score = 1.0 if structured_match else 0.0
        semantic_score = semantic_similarity or 0.0
        total_weight = (
            self._config.structured_weight * int(structured_enabled)
            + self._config.semantic_weight * int(semantic_enabled)
        )
        retrieval_score = 0.0
        if total_weight:
            retrieval_score = (
                self._config.structured_weight * structured_score
                + self._config.semantic_weight * semantic_score
            ) / total_weight
        return HybridCandidate(
            product=product,
            structured_match=structured_match,
            semantic_similarity=semantic_similarity,
            retrieval_score=retrieval_score,
        )
