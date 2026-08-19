"""Maintainable flooring domain rules kept separate from LLM prompts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from flooring_catalog.requirements.models import TrafficLevel, UsageType
from flooring_catalog.search.models import SearchProduct


class PreferenceFacts(Protocol):
    rooms: tuple[str, ...]
    has_pets: bool | None
    has_kids: bool | None
    traffic_level: TrafficLevel | None
    usage: UsageType | None
    durability_requirements: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuleAssessment:
    score: float
    reasons: tuple[str, ...]


def _identity(value: str | None) -> str:
    return value.strip().casefold() if value else ""


def _metadata_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(f"{key} {_metadata_text(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_metadata_text(item) for item in value)
    return str(value)


def _product_evidence(product: SearchProduct) -> str:
    """Use only fields confirmed by catalog profiling as rule evidence."""

    fields = (
        product.z_prod_type,
        product.material,
        product.style,
        product.description,
        product.waterproof,
    )
    metadata_fields = (
        "application",
        "application_facet",
        "construction",
        "features",
        "features_facet",
        "install_location",
        "surface_type",
        "usage",
        "warranty_text",
        "wear_layer",
        "wear_layer_thickness",
        "wear_layer_thickness_facet",
    )
    values = [*fields, *(product.metadata.get(key) for key in metadata_fields)]
    return " ".join(_metadata_text(value) for value in values).casefold()


def _affirmative(value: str | None) -> bool | None:
    normalized = _identity(value)
    if normalized in {"yes", "true", "1", "waterproof"}:
        return True
    if normalized in {"no", "false", "0", "not waterproof"}:
        return False
    return None


class FlooringBusinessRules:
    """Score room and household suitability using explicit domain rules."""

    _MOISTURE_ROOMS = frozenset({"bathroom", "basement", "kitchen", "laundry", "mudroom"})
    _DURABLE_TYPES = frozenset({"lvt", "laminate", "tile"})
    _DURABILITY_TERMS = (
        "commercial",
        "durable",
        "heavy traffic",
        "scratch resistant",
        "stain resistant",
        "wear layer",
    )

    def room_suitability(
        self, product: SearchProduct, preferences: PreferenceFacts
    ) -> RuleAssessment:
        rooms = {_identity(room) for room in preferences.rooms}
        if not rooms:
            return RuleAssessment(0.5, ("No room-specific preference was supplied.",))

        scores: list[float] = []
        reasons: list[str] = []
        waterproof = _affirmative(product.waterproof)
        product_type = _identity(product.z_prod_type)

        moisture_rooms = sorted(rooms & self._MOISTURE_ROOMS)
        if moisture_rooms:
            room_label = ", ".join(moisture_rooms)
            if waterproof is True:
                scores.append(1.0)
                reasons.append(f"Catalog marks the product waterproof for {room_label} use.")
            elif waterproof is False:
                scores.append(0.1)
                reasons.append(f"Catalog marks the product non-waterproof for {room_label} use.")
            else:
                scores.append(0.45)
                reasons.append(f"Waterproof status is unavailable for {room_label} use.")

        if "kitchen" in rooms:
            durability = self._durability_score(product)
            scores.append(durability)
            reasons.append("Kitchen use adds a durability and maintenance preference.")

        if "bedroom" in rooms:
            comfort_score = 1.0 if product_type == "carpet" else 0.7
            scores.append(comfort_score)
            reasons.append("Bedroom use gives additional weight to comfort-oriented flooring.")

        if not scores:
            return RuleAssessment(0.5, ("No specialized rule matched the supplied room.",))
        return RuleAssessment(sum(scores) / len(scores), tuple(reasons))

    def lifestyle_suitability(
        self, product: SearchProduct, preferences: PreferenceFacts
    ) -> RuleAssessment:
        applicable = any(
            (
                preferences.has_pets is True,
                preferences.has_kids is True,
                preferences.traffic_level is not None,
                preferences.usage is not None,
                preferences.durability_requirements,
            )
        )
        if not applicable:
            return RuleAssessment(0.5, ("No lifestyle-specific preference was supplied.",))

        evidence = _product_evidence(product)
        durability = self._durability_score(product)
        scores: list[float] = []
        reasons: list[str] = []

        if preferences.has_pets is True:
            pet_terms = ("pet", "scratch resistant", "stain resistant", "easy clean")
            pet_score = 1.0 if any(term in evidence for term in pet_terms) else durability
            scores.append(pet_score)
            reasons.append(
                "Pet use prioritizes scratch resistance, stain resistance, and cleaning."
            )

        if preferences.has_kids is True:
            kid_terms = ("stain resistant", "easy clean", "waterproof")
            kid_score = 1.0 if any(term in evidence for term in kid_terms) else durability
            scores.append(kid_score)
            reasons.append("Households with kids prioritize durability and easier maintenance.")

        if preferences.traffic_level is not None:
            if preferences.traffic_level is TrafficLevel.HIGH:
                scores.append(durability)
                reasons.append("High traffic applies the catalog-backed durability rule.")
            else:
                scores.append(max(0.6, durability))
                reasons.append("Low or medium traffic has a moderate durability requirement.")

        if preferences.usage is not None:
            if preferences.usage is UsageType.COMMERCIAL:
                commercial = "commercial" in evidence
                scores.append(1.0 if commercial else durability * 0.75)
                reasons.append("Commercial use prefers explicit commercial application evidence.")
            else:
                residential = "residential" in evidence
                scores.append(1.0 if residential else 0.65)
                reasons.append("Residential use prefers explicit residential application evidence.")

        for requirement in preferences.durability_requirements:
            normalized = _identity(requirement)
            if normalized:
                scores.append(1.0 if normalized in evidence else durability)
                reasons.append(f"Durability preference evaluated: {requirement}.")

        return RuleAssessment(sum(scores) / len(scores), tuple(reasons))

    def _durability_score(self, product: SearchProduct) -> float:
        evidence = _product_evidence(product)
        if any(term in evidence for term in self._DURABILITY_TERMS):
            return 1.0
        if _identity(product.z_prod_type) in self._DURABLE_TYPES:
            return 0.8
        return 0.5
