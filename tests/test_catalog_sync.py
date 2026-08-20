from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import flooring_catalog.catalog_sync as sync_module
from flooring_catalog.catalog_sync import synchronize_catalog
from flooring_catalog.embeddings import EMBEDDING_DIMENSIONS
from flooring_catalog.ingestion import IngestionStats


class FakeProvider:
    model = "test-model"
    dimensions = EMBEDDING_DIMENSIONS

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self.dimensions for _ in texts]


class FakeCursor:
    def __init__(self, *, lock_available: bool = True) -> None:
        self.lock_available = lock_available
        self.executions: list[tuple[str, object]] = []
        self.rowcount = 0
        self._row: tuple[bool] | None = None

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str, parameters: object = None) -> None:
        self.executions.append((statement, parameters))
        if "pg_try_advisory_lock" in statement:
            self._row = (self.lock_available,)
        elif "UPDATE catalog_products" in statement:
            self.rowcount = 3
            self._row = None
        else:
            self._row = None

    def fetchone(self) -> tuple[bool] | None:
        return self._row


class FakeConnection:
    def __init__(self, *, lock_available: bool = True) -> None:
        self.cursor_value = FakeCursor(lock_available=lock_available)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> FakeCursor:
        return self.cursor_value

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_catalog_sync_runs_ingestion_reconciliation_and_embeddings(monkeypatch) -> None:
    connection = FakeConnection()
    captured: dict[str, Any] = {}

    def fake_ingest(_connection, _path, **kwargs):  # type: ignore[no-untyped-def]
        captured["sync_id"] = kwargs["sync_id"]
        return IngestionStats(source_records=5, prepared_records=4, upserted_records=4)

    def fake_embeddings(_connection, _provider, **kwargs):  # type: ignore[no-untyped-def]
        captured["embedding_batch_size"] = kwargs["batch_size"]
        return SimpleNamespace(products_embedded=2)

    monkeypatch.setattr(sync_module, "ingest_catalog", fake_ingest)
    monkeypatch.setattr(sync_module, "update_product_embeddings", fake_embeddings)

    stats = synchronize_catalog(
        connection,  # type: ignore[arg-type]
        "complete-products.json",
        FakeProvider(),
        authoritative_snapshot=True,
        embedding_batch_size=25,
    )

    assert captured["sync_id"] == stats.run_id
    assert captured["embedding_batch_size"] == 25
    assert stats.source_records == 5
    assert stats.upserted_records == 4
    assert stats.rejected_records == 1
    assert stats.deactivated_records == 3
    assert stats.embedded_records == 2
    statements = [statement for statement, _ in connection.cursor_value.executions]
    assert any("INSERT INTO catalog_sync_runs" in statement for statement in statements)
    assert any("last_seen_sync_id IS DISTINCT FROM" in statement for statement in statements)
    assert any("finished_at" in statement for statement in statements)
    assert any("pg_advisory_unlock" in statement for statement in statements)


def test_catalog_sync_rejects_overlapping_runs(monkeypatch) -> None:
    connection = FakeConnection(lock_available=False)
    called = False

    def fake_ingest(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal called
        called = True

    monkeypatch.setattr(sync_module, "ingest_catalog", fake_ingest)
    with pytest.raises(RuntimeError, match="already running"):
        synchronize_catalog(  # type: ignore[arg-type]
            connection,
            "products.json",
            FakeProvider(),
        )
    assert called is False
