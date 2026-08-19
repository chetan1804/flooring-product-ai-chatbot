"""Convert ranked catalog candidates into factual recommendation cards."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol

from flooring_catalog.ranking.models import RankedCandidate
from flooring_catalog.recommendations.models import RecommendationCard
from flooring_catalog.recommendations.urls import ProductUrlBuilder
from flooring_catalog.search.models import SearchProduct


class RecommendationPreferences(Protocol):
    product_types: tuple[str, ...]
    brands: tuple[str, ...]
    materials: tuple[str, ...]
    colors: tuple[str, ...]
    styles: tuple[str, ...]
    rooms: tuple[str, ...]
    budget_min_per_sq_ft: Decimal | None
    budget_max_per_sq_ft: Decimal | None
    waterproof_required: bool | None
    has_pets: bool | None


def _identity(value: str | None) -> str:
    return value.strip().casefold() if value else ""


def _display_value(value: Any) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (list, tuple)):
        items = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return ", ".join(items) or None
    return None


class RecommendationCardService:
    """Present ranked products without LLM-generated facts or URLs."""

    _METADATA_ATTRIBUTES = {
        "application": "Application",
        "construction": "Construction",
        "features": "Features",
        "installation": "Installation",
        "wear_layer": "Wear layer",
    }

    def __init__(self, client_domain: str) -> None:
        self._urls = ProductUrlBuilder(client_domain)

    def build(
        self,
        ranked_candidates: list[RankedCandidate],
        preferences: RecommendationPreferences,
    ) -> list[RecommendationCard]:
        return [self._card(item, preferences) for item in ranked_candidates]

    def _card(
        self,
        ranked: RankedCandidate,
        preferences: RecommendationPreferences,
    ) -> RecommendationCard:
        product = ranked.candidate.product
        return RecommendationCard(
            sku=product.sku,
            name=product.name or product.sku,
            swatch=product.swatch,
            image=product.gallery_images or product.swatch,
            price=product.price,
            attributes=self._attributes(product),
            reasons=self._reasons(product, preferences),
            product_url=self._urls.for_sku(product.sku),
            ranking=ranked.score,
        )

    def _attributes(self, product: SearchProduct) -> dict[str, str]:
        attributes: dict[str, str] = {}
        dedicated = (
            ("Product type", product.z_prod_type),
            ("Brand", product.brand),
            ("Material", product.material),
            ("Color", product.color),
            ("Style", product.style),
            ("Waterproof", product.waterproof),
        )
        for label, value in dedicated:
            displayed = _display_value(value)
            if displayed:
                attributes[label] = displayed
        for field_name, label in self._METADATA_ATTRIBUTES.items():
            displayed = _display_value(product.metadata.get(field_name))
            if displayed:
                attributes[label] = displayed
        return attributes

    def _reasons(
        self,
        product: SearchProduct,
        preferences: RecommendationPreferences,
    ) -> tuple[str, ...]:
        """Explain matches using customer preferences and catalog values only."""

        reasons: list[str] = []
        comparisons = (
            ("product type", product.z_prod_type, preferences.product_types),
            ("brand", product.brand, preferences.brands),
            ("material", product.material, preferences.materials),
            ("color", product.color, preferences.colors),
            ("style", product.style, preferences.styles),
        )
        for label, catalog_value, requested_values in comparisons:
            if catalog_value and _identity(catalog_value) in {
                _identity(value) for value in requested_values
            }:
                reasons.append(f"Matches your requested {label}: {catalog_value}.")

        waterproof = _identity(product.waterproof) in {"yes", "true", "1", "waterproof"}
        if preferences.waterproof_required is True and waterproof:
            reasons.append(f"Catalog waterproof value is {product.waterproof}.")
        elif waterproof and preferences.rooms:
            rooms = ", ".join(preferences.rooms)
            reasons.append(
                f"Catalog waterproof value is {product.waterproof}, relevant to {rooms}."
            )

        if self._within_budget(product.price, preferences):
            reasons.append(f"Catalog price ${product.price} is within your requested budget.")

        if preferences.has_pets is True:
            features = _display_value(product.metadata.get("features"))
            if features and any(
                term in features.casefold()
                for term in ("pet", "scratch resistant", "stain resistant", "easy clean")
            ):
                reasons.append(f"Catalog features include: {features}.")

        if not reasons:
            if product.z_prod_type:
                reasons.append(f"Catalog identifies this as {product.z_prod_type} flooring.")
            else:
                reasons.append(f"Selected catalog product with SKU {product.sku}.")
        return tuple(reasons)

    @staticmethod
    def _within_budget(
        price: Decimal | None, preferences: RecommendationPreferences
    ) -> bool:
        if price is None:
            return False
        minimum = preferences.budget_min_per_sq_ft
        maximum = preferences.budget_max_per_sq_ft
        if minimum is None and maximum is None:
            return False
        return (minimum is None or price >= minimum) and (maximum is None or price <= maximum)
