"""Conservative deterministic mapping from customer language to catalog values."""

from __future__ import annotations

import re
from decimal import Decimal

from flooring_catalog.requirements.models import (
    CatalogVocabulary,
    CustomerRequirements,
    NormalizedRequirements,
)

PRODUCT_TYPE_ALIASES = {
    "luxury vinyl": "lvt",
    "luxury vinyl tile": "lvt",
    "luxury vinyl plank": "lvt",
    "vinyl plank": "lvt",
    "lvp": "lvt",
    "wood flooring": "hardwood",
}


def _identity(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


class CatalogRequirementMapper:
    """Map only exact, configured-alias, or unique containment matches."""

    def __init__(self, vocabulary: CatalogVocabulary) -> None:
        self._vocabulary = vocabulary

    @staticmethod
    def _map_values(
        requested: list[str],
        canonical_values: tuple[str, ...],
        aliases: dict[str, str] | None = None,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        canonical_by_identity = {_identity(value): value for value in canonical_values}
        aliases = aliases or {}
        mapped: list[str] = []
        unmapped: list[str] = []
        for requested_value in requested:
            requested_identity = _identity(requested_value)
            match = canonical_by_identity.get(requested_identity)
            if match is None and requested_identity in aliases:
                match = canonical_by_identity.get(_identity(aliases[requested_identity]))
            if match is None and len(requested_identity) >= 4:
                containment_matches = [
                    value
                    for identity, value in canonical_by_identity.items()
                    if requested_identity in identity
                ]
                if len(containment_matches) == 1:
                    match = containment_matches[0]
            if match is None:
                unmapped.append(requested_value)
            elif match not in mapped:
                mapped.append(match)
        return tuple(mapped), tuple(unmapped)

    def normalize(
        self, requirements: CustomerRequirements, *, customer_message: str
    ) -> NormalizedRequirements:
        mapped: dict[str, tuple[str, ...]] = {}
        unmapped: dict[str, tuple[str, ...]] = {}
        mappings = (
            (
                "product_types",
                requirements.product_types,
                self._vocabulary.product_types,
                PRODUCT_TYPE_ALIASES,
            ),
            ("brands", requirements.brands, self._vocabulary.brands, None),
            ("materials", requirements.materials, self._vocabulary.materials, None),
            ("colors", requirements.colors, self._vocabulary.colors, None),
            ("styles", requirements.styles, self._vocabulary.styles, None),
        )
        for field_name, requested, canonical, aliases in mappings:
            mapped_values, unmapped_values = self._map_values(requested, canonical, aliases)
            mapped[field_name] = mapped_values
            if unmapped_values:
                unmapped[field_name] = unmapped_values

        return NormalizedRequirements(
            **mapped,
            budget_min_per_sq_ft=(
                Decimal(str(requirements.budget_min_per_sq_ft))
                if requirements.budget_min_per_sq_ft is not None
                else None
            ),
            budget_max_per_sq_ft=(
                Decimal(str(requirements.budget_max_per_sq_ft))
                if requirements.budget_max_per_sq_ft is not None
                else None
            ),
            waterproof_required=requirements.waterproof_required,
            rooms=tuple(requirements.rooms),
            shades=tuple(requirements.shades),
            installation_preferences=tuple(requirements.installation_preferences),
            has_pets=requirements.has_pets,
            has_kids=requirements.has_kids,
            traffic_level=requirements.traffic_level,
            usage=requirements.usage,
            durability_requirements=tuple(requirements.durability_requirements),
            semantic_preferences=tuple(requirements.semantic_preferences),
            unmapped_catalog_terms=unmapped,
            semantic_query=customer_message.strip(),
        )
