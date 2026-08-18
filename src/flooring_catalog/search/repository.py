"""Safe PostgreSQL queries for exact and pgvector product retrieval."""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from flooring_catalog.embeddings import vector_literal
from flooring_catalog.search.models import SearchFilters, SearchProduct

SELECT_COLUMNS = """
sku, name, z_prod_type, swatch, price, brand, material, color, style,
description, gallery_images, waterproof, metadata
"""
MAX_CANDIDATE_LIMIT = 200


def _validated_limit(limit: int) -> int:
    if not 1 <= limit <= MAX_CANDIDATE_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_CANDIDATE_LIMIT}")
    return limit


def build_filter_clause(filters: SearchFilters) -> tuple[str, dict[str, Any]]:
    """Compile only allow-listed filter fields into SQL and bound parameters."""

    clauses = ["lower(btrim(status)) = 'active'", "btrim(swatch) <> ''"]
    parameters: dict[str, Any] = {}
    mappings = (
        ("z_prod_types", "z_prod_type"),
        ("brands", "brand"),
        ("materials", "material"),
        ("colors", "color"),
        ("styles", "style"),
    )
    for attribute, column in mappings:
        values = getattr(filters, attribute)
        if values:
            clauses.append(f"lower(btrim({column})) = ANY(%({attribute})s)")
            parameters[attribute] = list(values)
    if filters.minimum_price is not None:
        clauses.append("price >= %(minimum_price)s")
        parameters["minimum_price"] = filters.minimum_price
    if filters.maximum_price is not None:
        clauses.append("price <= %(maximum_price)s")
        parameters["maximum_price"] = filters.maximum_price
    if filters.waterproof is not None:
        clauses.append("lower(btrim(waterproof)) = ANY(%(waterproof_values)s)")
        parameters["waterproof_values"] = (
            ["yes", "true", "1"] if filters.waterproof else ["no", "false", "0"]
        )
    return " AND ".join(clauses), parameters


class ProductSearchRepository:
    """Database retrieval with fixed SQL shape and parameterized values."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def structured_search(self, filters: SearchFilters, *, limit: int) -> list[SearchProduct]:
        limit = _validated_limit(limit)
        where_sql, parameters = build_filter_clause(filters)
        parameters["limit"] = limit
        statement = f"""
SELECT {SELECT_COLUMNS}, NULL::double precision AS semantic_similarity
FROM catalog_products
WHERE {where_sql}
ORDER BY sku
LIMIT %(limit)s
"""
        return self._fetch_products(statement, parameters)

    def semantic_search(
        self,
        query_embedding: list[float],
        embedding_model: str,
        filters: SearchFilters,
        *,
        limit: int,
    ) -> list[SearchProduct]:
        limit = _validated_limit(limit)
        where_sql, parameters = build_filter_clause(filters)
        parameters.update(
            {
                "embedding": vector_literal(query_embedding),
                "embedding_model": embedding_model,
                "limit": limit,
            }
        )
        statement = f"""
SELECT {SELECT_COLUMNS},
       1 - (embedding <=> %(embedding)s::vector) AS semantic_similarity
FROM catalog_products
WHERE {where_sql}
  AND embedding IS NOT NULL
  AND embedding_model = %(embedding_model)s
ORDER BY embedding <=> %(embedding)s::vector, sku
LIMIT %(limit)s
"""
        return self._fetch_products(statement, parameters)

    def _fetch_products(self, statement: str, parameters: dict[str, Any]) -> list[SearchProduct]:
        with self._connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(statement, parameters)
            rows = cursor.fetchall()
        return [SearchProduct.from_row(row) for row in rows]

