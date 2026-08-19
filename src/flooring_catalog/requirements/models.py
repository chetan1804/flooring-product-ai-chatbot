"""Pydantic models for raw and catalog-normalized customer requirements."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from flooring_catalog.search.models import SearchFilters


class TrafficLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class UsageType(StrEnum):
    RESIDENTIAL = "residential"
    COMMERCIAL = "commercial"


StringList = Annotated[list[str], Field(default_factory=list, max_length=20)]


class CustomerRequirements(BaseModel):
    """Strict structured output produced from one customer message."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    product_types: StringList
    rooms: StringList
    materials: StringList
    colors: StringList
    shades: StringList
    styles: StringList
    brands: StringList
    budget_min_per_sq_ft: float | None = Field(default=None, ge=0)
    budget_max_per_sq_ft: float | None = Field(default=None, ge=0)
    waterproof_required: bool | None = None
    installation_preferences: StringList
    has_pets: bool | None = None
    has_kids: bool | None = None
    traffic_level: TrafficLevel | None = None
    usage: UsageType | None = None
    durability_requirements: StringList
    semantic_preferences: StringList

    @field_validator(
        "product_types",
        "rooms",
        "materials",
        "colors",
        "shades",
        "styles",
        "brands",
        "installation_preferences",
        "durability_requirements",
        "semantic_preferences",
        mode="after",
    )
    @classmethod
    def normalize_string_lists(cls, values: list[str]) -> list[str]:
        """Remove blank/duplicate model output without changing customer wording."""

        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            stripped = value.strip()
            identity = stripped.casefold()
            if stripped and identity not in seen:
                normalized.append(stripped)
                seen.add(identity)
        return normalized

    @model_validator(mode="after")
    def validate_budget_range(self) -> CustomerRequirements:
        if (
            self.budget_min_per_sq_ft is not None
            and self.budget_max_per_sq_ft is not None
            and self.budget_min_per_sq_ft > self.budget_max_per_sq_ft
        ):
            raise ValueError("budget minimum cannot exceed budget maximum")
        return self


class CatalogVocabulary(BaseModel):
    """Canonical values loaded from the current searchable catalog."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    product_types: tuple[str, ...] = ()
    brands: tuple[str, ...] = ()
    materials: tuple[str, ...] = ()
    colors: tuple[str, ...] = ()
    styles: tuple[str, ...] = ()


class NormalizedRequirements(BaseModel):
    """Validated requirements split into exact filters and contextual preferences."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    product_types: tuple[str, ...] = ()
    brands: tuple[str, ...] = ()
    materials: tuple[str, ...] = ()
    colors: tuple[str, ...] = ()
    styles: tuple[str, ...] = ()
    budget_min_per_sq_ft: Decimal | None = None
    budget_max_per_sq_ft: Decimal | None = None
    waterproof_required: bool | None = None
    rooms: tuple[str, ...] = ()
    shades: tuple[str, ...] = ()
    installation_preferences: tuple[str, ...] = ()
    has_pets: bool | None = None
    has_kids: bool | None = None
    traffic_level: TrafficLevel | None = None
    usage: UsageType | None = None
    durability_requirements: tuple[str, ...] = ()
    semantic_preferences: tuple[str, ...] = ()
    unmapped_catalog_terms: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    semantic_query: str

    def to_search_filters(self) -> SearchFilters:
        """Create the allow-listed Step 3 exact filters."""

        return SearchFilters(
            z_prod_types=self.product_types,
            brands=self.brands,
            materials=self.materials,
            colors=self.colors,
            styles=self.styles,
            minimum_price=self.budget_min_per_sq_ft,
            maximum_price=self.budget_max_per_sq_ft,
            waterproof=self.waterproof_required,
        )


class RequirementExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    extracted: CustomerRequirements
    normalized: NormalizedRequirements


def serializable_result(result: RequirementExtractionResult) -> dict[str, Any]:
    """Return JSON-compatible output for CLI/API boundaries."""

    return result.model_dump(mode="json")

