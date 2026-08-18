from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from typing import Any

import pytest

from flooring_catalog.embeddings import EMBEDDING_DIMENSIONS
from flooring_catalog.search.models import SearchFilters, SearchProduct
from flooring_catalog.search.repository import ProductSearchRepository, build_filter_clause
from flooring_catalog.search.service import HybridSearchConfig, HybridSearchService


def product(sku: str, similarity: float | None = None) -> SearchProduct:
    return SearchProduct(
        sku=sku,
        name=sku,
        z_prod_type="lvt",
        swatch="image.jpg",
        price=None,
        brand=None,
        material=None,
        color=None,
        style=None,
        description=None,
        gallery_images=None,
        waterproof="Yes",
        metadata={},
        semantic_similarity=similarity,
    )


def test_search_filters_normalize_and_validate_values() -> None:
    filters = SearchFilters(
        z_prod_types=(" LVT ", "lvt"),
        brands=("Shaw Floors",),
        minimum_price=Decimal("10"),
        maximum_price=Decimal("20"),
    )
    assert filters.z_prod_types == ("lvt",)
    assert filters.brands == ("shaw floors",)
    assert filters.active
    with pytest.raises(ValueError, match="cannot exceed"):
        SearchFilters(minimum_price=Decimal("20"), maximum_price=Decimal("10"))


def test_filter_values_are_parameters_not_sql() -> None:
    malicious = "lvt'); drop table catalog_products; --"
    clause, parameters = build_filter_clause(SearchFilters(z_prod_types=(malicious,)))
    assert malicious not in clause
    assert parameters["z_prod_types"] == [malicious]
    assert "z_prod_type" in clause


def test_filter_clause_supports_exact_price_and_waterproof_requirements() -> None:
    clause, parameters = build_filter_clause(
        SearchFilters(minimum_price=Decimal("2"), maximum_price=Decimal("8"), waterproof=True)
    )
    assert "price >= %(minimum_price)s" in clause
    assert "price <= %(maximum_price)s" in clause
    assert parameters["waterproof_values"] == ["yes", "true", "1"]


class CapturingCursor:
    def __init__(self, connection: CapturingConnection) -> None:
        self.connection = connection

    def __enter__(self) -> CapturingCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str, parameters: dict[str, Any]) -> None:
        self.connection.statement = statement
        self.connection.parameters = parameters

    def fetchall(self) -> list[dict[str, Any]]:
        return self.connection.rows


class CapturingConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.statement = ""
        self.parameters: dict[str, Any] = {}

    def cursor(self, **_kwargs: Any) -> CapturingCursor:
        return CapturingCursor(self)


def test_semantic_repository_uses_pgvector_with_bound_exact_filters() -> None:
    row = asdict(product("A", 0.75))
    connection = CapturingConnection([row])
    repository = ProductSearchRepository(connection)  # type: ignore[arg-type]
    result = repository.semantic_search(
        [1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1),
        "test-model",
        SearchFilters(z_prod_types=("lvt",), waterproof=True),
        limit=5,
    )
    assert result[0].semantic_similarity == 0.75
    assert "embedding <=> %(embedding)s::vector" in connection.statement
    assert "lower(btrim(z_prod_type))" in connection.statement
    assert connection.parameters["z_prod_types"] == ["lvt"]
    assert connection.parameters["embedding_model"] == "test-model"
    assert connection.parameters["limit"] == 5


class FakeProvider:
    model = "test-model"
    dimensions = EMBEDDING_DIMENSIONS

    def __init__(self) -> None:
        self.inputs: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.inputs.extend(texts)
        return [[1.0] + [0.0] * (EMBEDDING_DIMENSIONS - 1)]


class FakeRepository:
    def __init__(self) -> None:
        self.structured = [product("A"), product("B")]
        self.semantic = [product("B", 0.9), product("C", 0.8)]
        self.semantic_filters: SearchFilters | None = None

    def structured_search(self, filters: SearchFilters, *, limit: int) -> list[SearchProduct]:
        assert filters.active
        assert limit == 10
        return self.structured

    def semantic_search(
        self,
        query_embedding: list[float],
        embedding_model: str,
        filters: SearchFilters,
        *,
        limit: int,
    ) -> list[SearchProduct]:
        assert len(query_embedding) == EMBEDDING_DIMENSIONS
        assert embedding_model == "test-model"
        assert limit == 10
        self.semantic_filters = filters
        return self.semantic


def test_hybrid_search_unions_candidates_and_prefers_exact_filtered_semantic_matches() -> None:
    repository = FakeRepository()
    provider = FakeProvider()
    service = HybridSearchService(
        repository,  # type: ignore[arg-type]
        provider,
        HybridSearchConfig(candidate_limit=10, result_limit=3),
    )
    filters = SearchFilters(z_prod_types=("lvt",))
    results = service.search(query="warm natural oak", filters=filters)
    assert [result.product.sku for result in results] == ["B", "C", "A"]
    assert all(result.structured_match for result in results)
    assert results[0].retrieval_score > results[1].retrieval_score > results[2].retrieval_score
    assert repository.semantic_filters == filters
    assert provider.inputs == ["warm natural oak"]


def test_structured_only_search_does_not_need_embedding_provider() -> None:
    service = HybridSearchService(
        FakeRepository(),  # type: ignore[arg-type]
        None,
        HybridSearchConfig(candidate_limit=10, result_limit=2),
    )
    results = service.search(query=None, filters=SearchFilters(brands=("shaw",)))
    assert [result.product.sku for result in results] == ["A", "B"]
    assert all(result.retrieval_score == 1.0 for result in results)


def test_search_requires_query_or_filter() -> None:
    service = HybridSearchService(FakeRepository(), FakeProvider())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="query or at least one"):
        service.search(query=" ", filters=SearchFilters())


def test_semantic_search_requires_provider() -> None:
    service = HybridSearchService(FakeRepository(), None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="embedding provider"):
        service.search(query="oak", filters=SearchFilters())
