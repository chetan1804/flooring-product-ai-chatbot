"""Product embedding text construction and batch vector generation."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from openai import OpenAI
from psycopg import Connection

EMBEDDING_DIMENSIONS = 1536
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_METADATA_FIELDS = (
    "application",
    "construction",
    "design",
    "design_style",
    "features",
    "fiber",
    "finish",
    "lifestyle",
    "look",
    "pattern",
    "shade",
    "species",
    "sub_type",
    "surface_type",
    "usage",
    "wear_layer",
)

SELECT_EMBEDDING_PRODUCTS_SQL = """
SELECT sku, name, z_prod_type, brand, material, color, style,
       description, waterproof, metadata
FROM catalog_products
WHERE sku > %(after_sku)s
  AND (embedding IS NULL OR embedding_model IS DISTINCT FROM %(model)s)
ORDER BY sku
LIMIT %(limit)s
"""

UPDATE_EMBEDDING_SQL = """
UPDATE catalog_products
SET embedding = %(embedding)s::vector,
    embedding_model = %(model)s,
    embedding_updated_at = now()
WHERE sku = %(sku)s
"""


class EmbeddingProvider(Protocol):
    """Provider boundary used by production code and deterministic tests."""

    model: str
    dimensions: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one vector for every input text in the original order."""


@dataclass(frozen=True, slots=True)
class EmbeddingSettings:
    model: str = DEFAULT_EMBEDDING_MODEL
    dimensions: int = EMBEDDING_DIMENSIONS
    batch_size: int = 100
    max_text_characters: int = 12_000

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> EmbeddingSettings:
        values = os.environ if environ is None else environ
        model = values.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip()
        if not model:
            raise ValueError("EMBEDDING_MODEL cannot be empty")
        try:
            dimensions = int(values.get("EMBEDDING_DIMENSIONS", str(EMBEDDING_DIMENSIONS)))
            batch_size = int(values.get("EMBEDDING_BATCH_SIZE", "100"))
            max_characters = int(values.get("EMBEDDING_MAX_TEXT_CHARS", "12000"))
        except ValueError as error:
            raise ValueError("embedding numeric settings must be integers") from error
        if dimensions != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"EMBEDDING_DIMENSIONS must match database vector({EMBEDDING_DIMENSIONS})"
            )
        if batch_size <= 0:
            raise ValueError("EMBEDDING_BATCH_SIZE must be positive")
        if max_characters <= 0:
            raise ValueError("EMBEDDING_MAX_TEXT_CHARS must be positive")
        return cls(
            model=model,
            dimensions=dimensions,
            batch_size=batch_size,
            max_text_characters=max_characters,
        )


class OpenAIEmbeddingProvider:
    """Official OpenAI SDK adapter with explicit model and vector dimensions."""

    def __init__(
        self,
        settings: EmbeddingSettings,
        *,
        client: OpenAI | None = None,
    ) -> None:
        self.model = settings.model
        self.dimensions = settings.dimensions
        self._client = client or OpenAI()

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(
            input=list(texts),
            model=self.model,
            dimensions=self.dimensions,
            encoding_format="float",
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [list(item.embedding) for item in ordered]
        if len(vectors) != len(texts):
            raise ValueError("embedding provider returned an unexpected number of vectors")
        for vector in vectors:
            validate_embedding(vector, self.dimensions)
        return vectors


def validate_embedding(vector: Sequence[float], dimensions: int = EMBEDDING_DIMENSIONS) -> None:
    if len(vector) != dimensions:
        raise ValueError(f"embedding must contain exactly {dimensions} values")
    if any(not math.isfinite(float(value)) for value in vector):
        raise ValueError("embedding values must be finite")


def vector_literal(vector: Sequence[float]) -> str:
    """Serialize a validated vector for a parameterized pgvector cast."""

    validate_embedding(vector)
    return "[" + ",".join(format(float(value), ".17g") for value in vector) + "]"


def _text_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, list):
        values = [str(item).strip() for item in value if str(item).strip()]
        return ", ".join(values) or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def build_embedding_text(product: Mapping[str, Any], *, max_characters: int = 12_000) -> str:
    """Build semantic text exclusively from confirmed catalog attributes."""

    if max_characters <= 0:
        raise ValueError("max_characters must be positive")
    labelled_fields = (
        ("Name", product.get("name")),
        ("Product type", product.get("z_prod_type")),
        ("Brand", product.get("brand")),
        ("Material", product.get("material")),
        ("Color", product.get("color")),
        ("Style", product.get("style")),
        ("Waterproof", product.get("waterproof")),
        ("Description", product.get("description")),
    )
    parts = [f"{label}: {text}" for label, value in labelled_fields if (text := _text_value(value))]
    metadata = product.get("metadata")
    if isinstance(metadata, dict):
        for key in EMBEDDING_METADATA_FIELDS:
            if text := _text_value(metadata.get(key)):
                parts.append(f"{key.replace('_', ' ').title()}: {text}")
    text = "\n".join(parts) or f"SKU: {_text_value(product.get('sku')) or 'unknown'}"
    return text[:max_characters]


@dataclass(slots=True)
class EmbeddingUpdateStats:
    products_embedded: int = 0
    batches_committed: int = 0


def update_product_embeddings(
    connection: Connection,
    provider: EmbeddingProvider,
    *,
    batch_size: int = 100,
    max_text_characters: int = 12_000,
) -> EmbeddingUpdateStats:
    """Generate missing/stale embeddings and commit each bounded batch."""

    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if provider.dimensions != EMBEDDING_DIMENSIONS:
        raise ValueError(f"provider dimensions must be {EMBEDDING_DIMENSIONS}")

    stats = EmbeddingUpdateStats()
    after_sku = ""
    while True:
        with connection.cursor() as cursor:
            cursor.execute(
                SELECT_EMBEDDING_PRODUCTS_SQL,
                {"after_sku": after_sku, "model": provider.model, "limit": batch_size},
            )
            columns = [column.name for column in cursor.description]
            rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        if not rows:
            break

        texts = [
            build_embedding_text(row, max_characters=max_text_characters) for row in rows
        ]
        vectors = provider.embed(texts)
        if len(vectors) != len(rows):
            raise ValueError("embedding provider returned an unexpected number of vectors")
        parameters = [
            {
                "sku": row["sku"],
                "model": provider.model,
                "embedding": vector_literal(vector),
            }
            for row, vector in zip(rows, vectors, strict=True)
        ]
        try:
            with connection.cursor() as cursor:
                cursor.executemany(UPDATE_EMBEDDING_SQL, parameters)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        stats.products_embedded += len(rows)
        stats.batches_committed += 1
        after_sku = str(rows[-1]["sku"])
    return stats
