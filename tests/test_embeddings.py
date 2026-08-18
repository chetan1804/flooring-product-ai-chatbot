from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from flooring_catalog.embeddings import (
    EMBEDDING_DIMENSIONS,
    EmbeddingSettings,
    OpenAIEmbeddingProvider,
    build_embedding_text,
    update_product_embeddings,
    vector_literal,
)


def _vector(first: float = 1.0) -> list[float]:
    return [first] + [0.0] * (EMBEDDING_DIMENSIONS - 1)


def test_embedding_settings_are_validated() -> None:
    settings = EmbeddingSettings.from_env(
        {
            "EMBEDDING_MODEL": "text-embedding-3-small",
            "EMBEDDING_DIMENSIONS": "1536",
            "EMBEDDING_BATCH_SIZE": "25",
        }
    )
    assert settings.batch_size == 25
    with pytest.raises(ValueError, match="must match database"):
        EmbeddingSettings.from_env({"EMBEDDING_DIMENSIONS": "128"})


def test_embedding_text_uses_confirmed_fields_and_selected_metadata() -> None:
    text = build_embedding_text(
        {
            "sku": "A",
            "name": "Coastal Oak",
            "z_prod_type": "lvt",
            "color": "Light Oak",
            "metadata": {"look": "Natural", "client_code": "PRIVATE", "unknown": "ignored"},
        }
    )
    assert "Name: Coastal Oak" in text
    assert "Product type: lvt" in text
    assert "Look: Natural" in text
    assert "PRIVATE" not in text
    assert "ignored" not in text


def test_embedding_text_is_bounded() -> None:
    assert len(build_embedding_text({"description": "x" * 100}, max_characters=20)) == 20


def test_vector_literal_validates_size_and_finite_values() -> None:
    literal = vector_literal(_vector())
    assert literal.startswith("[1,")
    with pytest.raises(ValueError, match="exactly 1536"):
        vector_literal([1.0])
    with pytest.raises(ValueError, match="finite"):
        vector_literal([float("nan")] + [0.0] * (EMBEDDING_DIMENSIONS - 1))


class FakeEmbeddingsEndpoint:
    def __init__(self) -> None:
        self.arguments: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> Any:
        self.arguments = kwargs
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=_vector(0.5)),
                SimpleNamespace(index=0, embedding=_vector(1.0)),
            ]
        )


def test_openai_provider_batches_and_restores_response_order() -> None:
    endpoint = FakeEmbeddingsEndpoint()
    client = SimpleNamespace(embeddings=endpoint)
    provider = OpenAIEmbeddingProvider(EmbeddingSettings(), client=client)  # type: ignore[arg-type]
    vectors = provider.embed(["first", "second"])
    assert vectors[0][0] == 1.0
    assert vectors[1][0] == 0.5
    assert endpoint.arguments == {
        "input": ["first", "second"],
        "model": "text-embedding-3-small",
        "dimensions": 1536,
        "encoding_format": "float",
    }


class DeterministicProvider:
    model = "test-model"
    dimensions = EMBEDDING_DIMENSIONS

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_vector(float(index + 1)) for index, _ in enumerate(texts)]


@dataclass
class Description:
    name: str


class FakeEmbeddingCursor:
    def __init__(self, connection: FakeEmbeddingConnection) -> None:
        self.connection = connection
        self.description: list[Description] = []

    def __enter__(self) -> FakeEmbeddingCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, _statement: str, _parameters: dict[str, Any]) -> None:
        self.description = [Description(name) for name in self.connection.columns]

    def fetchall(self) -> list[tuple[Any, ...]]:
        if self.connection.select_calls:
            return []
        self.connection.select_calls += 1
        return [
            tuple(row[column] for column in self.connection.columns)
            for row in self.connection.rows
        ]

    def executemany(self, _statement: str, parameters: list[dict[str, Any]]) -> None:
        self.connection.updates.extend(parameters)


class FakeEmbeddingConnection:
    columns = [
        "sku", "name", "z_prod_type", "brand", "material", "color", "style",
        "description", "waterproof", "metadata",
    ]

    def __init__(self) -> None:
        self.rows = [
            {"sku": "A", "name": "Oak", "z_prod_type": "lvt", "brand": None,
             "material": None, "color": None, "style": None, "description": None,
             "waterproof": "Yes", "metadata": {}},
            {"sku": "B", "name": "Maple", "z_prod_type": "hardwood", "brand": None,
             "material": None, "color": None, "style": None, "description": None,
             "waterproof": "No", "metadata": {}},
        ]
        self.select_calls = 0
        self.updates: list[dict[str, Any]] = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> FakeEmbeddingCursor:
        return FakeEmbeddingCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_embedding_update_reads_and_commits_batches() -> None:
    connection = FakeEmbeddingConnection()
    stats = update_product_embeddings(
        connection, DeterministicProvider(), batch_size=2  # type: ignore[arg-type]
    )
    assert stats.products_embedded == 2
    assert stats.batches_committed == 1
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert [update["sku"] for update in connection.updates] == ["A", "B"]
    assert all(update["model"] == "test-model" for update in connection.updates)
