from __future__ import annotations

import json
import os

import psycopg
import pytest

from flooring_catalog.database.schema import apply_schema
from flooring_catalog.ingestion import ingest_catalog

pytestmark = pytest.mark.integration


def test_real_postgres_schema_and_upsert(tmp_path) -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    path = tmp_path / "products.json"
    path.write_text(
        json.dumps(
            [{"sku": "CODEX_STEP2_TEST", "name": "Test Oak", "status": "active",
              "swatch": "test.jpg", "z_prod_type": "lvt", "price": 0}]
        ),
        encoding="utf-8",
    )
    with psycopg.connect(database_url) as connection:
        apply_schema(connection)
        first = ingest_catalog(connection, path, batch_size=10)
        second = ingest_catalog(connection, path, batch_size=10)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*), max(price) FROM catalog_products WHERE sku = %s",
                ("CODEX_STEP2_TEST",),
            )
            count, price = cursor.fetchone()
            cursor.execute("DELETE FROM catalog_products WHERE sku = %s", ("CODEX_STEP2_TEST",))
        connection.commit()

    assert first.upserted_records == 1
    assert second.upserted_records == 1
    assert count == 1
    assert price is None

