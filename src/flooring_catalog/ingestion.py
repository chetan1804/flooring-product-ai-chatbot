"""Normalization and transactional batch ingestion for eligible catalog products."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg import Connection

from flooring_catalog.streaming import iter_json_array
from flooring_catalog.validation import has_active_status, has_valid_swatch

DEDICATED_FIELDS = frozenset(
    {
        "sku",
        "name",
        "z_prod_type",
        "status",
        "swatch",
        "price",
        "brand",
        "material",
        "color",
        "style",
        "description",
        "gallery_images",
        "waterproof",
    }
)

UPSERT_PRODUCT_SQL = """
INSERT INTO catalog_products (
    sku, name, z_prod_type, status, swatch, price, brand, material,
    color, style, description, gallery_images, waterproof, metadata, last_seen_sync_id
) VALUES (
    %(sku)s, %(name)s, %(z_prod_type)s, %(status)s, %(swatch)s, %(price)s,
    %(brand)s, %(material)s, %(color)s, %(style)s, %(description)s,
    %(gallery_images)s, %(waterproof)s, %(metadata)s::jsonb, %(last_seen_sync_id)s
)
ON CONFLICT (sku) DO UPDATE SET
    name = EXCLUDED.name,
    z_prod_type = EXCLUDED.z_prod_type,
    status = EXCLUDED.status,
    swatch = EXCLUDED.swatch,
    price = EXCLUDED.price,
    brand = EXCLUDED.brand,
    material = EXCLUDED.material,
    color = EXCLUDED.color,
    style = EXCLUDED.style,
    description = EXCLUDED.description,
    gallery_images = EXCLUDED.gallery_images,
    waterproof = EXCLUDED.waterproof,
    metadata = EXCLUDED.metadata,
    last_seen_sync_id = EXCLUDED.last_seen_sync_id,
    updated_at = now()
"""


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def normalize_price(value: Any) -> Decimal | None:
    """Return a positive price or NULL for missing/zero/invalid placeholders."""

    if value is None or isinstance(value, bool):
        return None
    try:
        price = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return price if price.is_finite() and price > 0 else None


@dataclass(frozen=True, slots=True)
class ProductRecord:
    sku: str
    name: str | None
    z_prod_type: str | None
    status: str
    swatch: str
    price: Decimal | None
    brand: str | None
    material: str | None
    color: str | None
    style: str | None
    description: str | None
    gallery_images: str | None
    waterproof: str | None
    metadata: dict[str, Any]

    def parameters(self, *, sync_id: UUID | None = None) -> dict[str, Any]:
        values = {
            "sku": self.sku,
            "name": self.name,
            "z_prod_type": self.z_prod_type,
            "status": self.status,
            "swatch": self.swatch,
            "price": self.price,
            "brand": self.brand,
            "material": self.material,
            "color": self.color,
            "style": self.style,
            "description": self.description,
            "gallery_images": self.gallery_images,
            "waterproof": self.waterproof,
            # Passing serialized JSON keeps the SQL cast explicit and parameterized.
            "metadata": json.dumps(self.metadata, ensure_ascii=False, separators=(",", ":")),
            "last_seen_sync_id": sync_id,
        }
        return values


def normalize_product(product: dict[str, Any]) -> tuple[ProductRecord | None, str | None]:
    """Map one source object into the confirmed schema or return a rejection reason."""

    if not has_active_status(product):
        return None, "status_not_active"
    if not has_valid_swatch(product):
        return None, "invalid_swatch"
    sku = _optional_text(product.get("sku"))
    if sku is None:
        return None, "missing_sku"
    swatch = _optional_text(product.get("swatch"))
    if swatch is None:
        return None, "unsupported_swatch_type"

    metadata = {key: value for key, value in product.items() if key not in DEDICATED_FIELDS}
    return (
        ProductRecord(
            sku=sku,
            name=_optional_text(product.get("name")),
            z_prod_type=_optional_text(product.get("z_prod_type")),
            status="active",
            swatch=swatch,
            price=normalize_price(product.get("price")),
            brand=_optional_text(product.get("brand")),
            material=_optional_text(product.get("material")),
            color=_optional_text(product.get("color")),
            style=_optional_text(product.get("style")),
            description=_optional_text(product.get("description")),
            gallery_images=_optional_text(product.get("gallery_images")),
            waterproof=_optional_text(product.get("waterproof")),
            metadata=metadata,
        ),
        None,
    )


@dataclass(slots=True)
class IngestionStats:
    source_records: int = 0
    prepared_records: int = 0
    upserted_records: int = 0
    batches_committed: int = 0
    status_not_active: int = 0
    invalid_swatch: int = 0
    missing_sku: int = 0
    unsupported_swatch_type: int = 0

    @property
    def rejected_records(self) -> int:
        return self.source_records - self.prepared_records


def _write_batch(
    connection: Connection,
    batch: list[ProductRecord],
    *,
    sync_id: UUID | None = None,
) -> None:
    try:
        with connection.cursor() as cursor:
            cursor.executemany(
                UPSERT_PRODUCT_SQL,
                [record.parameters(sync_id=sync_id) for record in batch],
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def ingest_catalog(
    connection: Connection,
    catalog_path: str | Path,
    *,
    batch_size: int = 1000,
    sync_id: UUID | None = None,
) -> IngestionStats:
    """Stream, filter, normalize, and upsert a catalog in committed batches."""

    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    stats = IngestionStats()
    batch: list[ProductRecord] = []

    for product in iter_json_array(catalog_path):
        stats.source_records += 1
        record, rejection = normalize_product(product)
        if record is None:
            setattr(stats, rejection, getattr(stats, rejection) + 1)
            continue
        stats.prepared_records += 1
        batch.append(record)
        if len(batch) >= batch_size:
            _write_batch(connection, batch, sync_id=sync_id)
            stats.upserted_records += len(batch)
            stats.batches_committed += 1
            batch.clear()

    if batch:
        _write_batch(connection, batch, sync_id=sync_id)
        stats.upserted_records += len(batch)
        stats.batches_committed += 1
    return stats
