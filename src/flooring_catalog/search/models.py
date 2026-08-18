"""Validated data structures shared by retrieval layers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


def _normalized_values(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value.strip().casefold() for value in values if value.strip()))


@dataclass(frozen=True, slots=True)
class SearchFilters:
    """Allow-listed exact filters; no field or SQL expression comes from a caller."""

    z_prod_types: tuple[str, ...] = ()
    brands: tuple[str, ...] = ()
    materials: tuple[str, ...] = ()
    colors: tuple[str, ...] = ()
    styles: tuple[str, ...] = ()
    minimum_price: Decimal | None = None
    maximum_price: Decimal | None = None
    waterproof: bool | None = None

    def __post_init__(self) -> None:
        for field_name in ("z_prod_types", "brands", "materials", "colors", "styles"):
            object.__setattr__(self, field_name, _normalized_values(getattr(self, field_name)))
        if self.minimum_price is not None and self.minimum_price < 0:
            raise ValueError("minimum_price cannot be negative")
        if self.maximum_price is not None and self.maximum_price < 0:
            raise ValueError("maximum_price cannot be negative")
        if (
            self.minimum_price is not None
            and self.maximum_price is not None
            and self.minimum_price > self.maximum_price
        ):
            raise ValueError("minimum_price cannot exceed maximum_price")

    @property
    def active(self) -> bool:
        return any(
            (
                self.z_prod_types,
                self.brands,
                self.materials,
                self.colors,
                self.styles,
                self.minimum_price is not None,
                self.maximum_price is not None,
                self.waterproof is not None,
            )
        )


@dataclass(frozen=True, slots=True)
class SearchProduct:
    sku: str
    name: str | None
    z_prod_type: str | None
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
    semantic_similarity: float | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> SearchProduct:
        return cls(
            sku=row["sku"],
            name=row.get("name"),
            z_prod_type=row.get("z_prod_type"),
            swatch=row["swatch"],
            price=row.get("price"),
            brand=row.get("brand"),
            material=row.get("material"),
            color=row.get("color"),
            style=row.get("style"),
            description=row.get("description"),
            gallery_images=row.get("gallery_images"),
            waterproof=row.get("waterproof"),
            metadata=row.get("metadata") or {},
            semantic_similarity=(
                float(row["semantic_similarity"])
                if row.get("semantic_similarity") is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class HybridCandidate:
    product: SearchProduct
    structured_match: bool
    semantic_similarity: float | None
    retrieval_score: float

