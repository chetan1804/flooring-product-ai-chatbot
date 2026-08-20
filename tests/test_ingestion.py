from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from flooring_catalog.ingestion import (
    UPSERT_PRODUCT_SQL,
    ingest_catalog,
    normalize_price,
    normalize_product,
)


class FakeCursor:
    def __init__(self, batches: list[list[dict[str, Any]]]) -> None:
        self.batches = batches

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def executemany(self, statement: str, parameters: list[dict[str, Any]]) -> None:
        assert statement == UPSERT_PRODUCT_SQL
        self.batches.append(parameters)


class FakeConnection:
    def __init__(self) -> None:
        self.batches: list[list[dict[str, Any]]] = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self.batches)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


@pytest.mark.parametrize(
    "value",
    [None, "", " ", 0, 0.0, "0.00", -1, False, "invalid", "NaN", "Infinity"],
)
def test_unavailable_price_becomes_null(value: object) -> None:
    assert normalize_price(value) is None


def test_positive_price_is_preserved_exactly() -> None:
    assert normalize_price("12.34") == Decimal("12.34")


def test_normalization_uses_dedicated_columns_and_jsonb_metadata() -> None:
    product = {
        "sku": " SKU-1 ",
        "name": "Oak",
        "status": " ACTIVE ",
        "swatch": " image.jpg ",
        "z_prod_type": "lvt",
        "price": 0,
        "brand": "Example",
        "wear_layer": "20 mil",
        "custom": {"source": "catalog"},
    }
    record, rejection = normalize_product(product)
    assert rejection is None
    assert record is not None
    assert record.sku == "SKU-1"
    assert record.status == "active"
    assert record.swatch == "image.jpg"
    assert record.price is None
    assert record.metadata == {"wear_layer": "20 mil", "custom": {"source": "catalog"}}
    assert "sku" not in record.metadata


@pytest.mark.parametrize(
    ("product", "reason"),
    [
        ({"sku": "A", "status": "inactive", "swatch": "x"}, "status_not_active"),
        ({"sku": "A", "status": "active", "swatch": " "}, "invalid_swatch"),
        ({"status": "active", "swatch": "x"}, "missing_sku"),
        ({"sku": "A", "status": "active", "swatch": ["x"]}, "unsupported_swatch_type"),
    ],
)
def test_invalid_products_are_rejected(product: dict[str, object], reason: str) -> None:
    record, actual_reason = normalize_product(product)
    assert record is None
    assert actual_reason == reason


def test_catalog_is_filtered_and_written_in_batches(tmp_path) -> None:
    products = [
        {"sku": "A", "status": "active", "swatch": "a.jpg"},
        {"sku": "B", "status": "active", "swatch": "b.jpg"},
        {"sku": "C", "status": "inactive", "swatch": "c.jpg"},
        {"sku": "D", "status": "active", "swatch": "d.jpg"},
        {"sku": "E", "status": "active", "swatch": " "},
    ]
    path = tmp_path / "products.json"
    path.write_text(json.dumps(products), encoding="utf-8")
    connection = FakeConnection()

    stats = ingest_catalog(connection, path, batch_size=2)  # type: ignore[arg-type]

    assert [len(batch) for batch in connection.batches] == [2, 1]
    assert connection.commits == 2
    assert connection.rollbacks == 0
    assert stats.source_records == 5
    assert stats.prepared_records == 3
    assert stats.upserted_records == 3
    assert stats.rejected_records == 2
    assert stats.status_not_active == 1
    assert stats.invalid_swatch == 1


def test_sync_id_is_written_with_every_upsert(tmp_path) -> None:
    path = tmp_path / "products.json"
    path.write_text(
        json.dumps([{"sku": "A", "status": "active", "swatch": "a.jpg"}]),
        encoding="utf-8",
    )
    connection = FakeConnection()
    sync_id = UUID("d24d7537-d249-4b00-9690-1c11676a4052")
    ingest_catalog(connection, path, sync_id=sync_id)  # type: ignore[arg-type]
    assert connection.batches[0][0]["last_seen_sync_id"] == sync_id


def test_batch_size_must_be_positive(tmp_path) -> None:
    with pytest.raises(ValueError, match="batch_size must be positive"):
        ingest_catalog(FakeConnection(), tmp_path / "unused.json", batch_size=0)  # type: ignore[arg-type]
