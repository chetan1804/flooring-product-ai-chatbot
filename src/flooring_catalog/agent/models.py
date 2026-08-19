"""Serializable state models for multi-turn flooring conversations."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from flooring_catalog.ranking.models import RankingScore
from flooring_catalog.recommendations.models import RecommendationCard
from flooring_catalog.requirements.models import (
    NormalizedRequirements,
    TrafficLevel,
    UsageType,
)
from flooring_catalog.search.models import SearchFilters


def _merge_values(existing: tuple[str, ...], incoming: tuple[str, ...]) -> tuple[str, ...]:
    merged = list(existing)
    identities = {value.casefold() for value in existing}
    for value in incoming:
        if value.casefold() not in identities:
            merged.append(value)
            identities.add(value.casefold())
    return tuple(merged)


class AgentAction(StrEnum):
    CLARIFY = "clarify"
    CANDIDATES = "candidates"
    NO_RESULTS = "no_results"


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: ChatRole
    content: str = Field(min_length=1, max_length=10_000)


class ConversationPreferences(BaseModel):
    """Accumulated validated preferences for one LangGraph thread."""

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

    def merge(self, incoming: NormalizedRequirements) -> ConversationPreferences:
        """Accumulate new facts, preserving previously supplied preferences."""

        tuple_fields = (
            "product_types",
            "brands",
            "materials",
            "colors",
            "styles",
            "rooms",
            "shades",
            "installation_preferences",
            "durability_requirements",
            "semantic_preferences",
        )
        values = {
            field_name: _merge_values(getattr(self, field_name), getattr(incoming, field_name))
            for field_name in tuple_fields
        }
        minimum = incoming.budget_min_per_sq_ft
        maximum = incoming.budget_max_per_sq_ft
        minimum = self.budget_min_per_sq_ft if minimum is None else minimum
        maximum = self.budget_max_per_sq_ft if maximum is None else maximum
        if minimum is not None and maximum is not None and minimum > maximum:
            if incoming.budget_min_per_sq_ft is not None:
                maximum = None
            else:
                minimum = None

        unmapped = dict(self.unmapped_catalog_terms)
        for field_name in ("product_types", "brands", "materials", "colors", "styles"):
            incoming_mapped = getattr(incoming, field_name)
            incoming_unmapped = incoming.unmapped_catalog_terms.get(field_name)
            if incoming_mapped:
                unmapped.pop(field_name, None)
            elif incoming_unmapped:
                unmapped[field_name] = incoming_unmapped

        return ConversationPreferences(
            **values,
            budget_min_per_sq_ft=minimum,
            budget_max_per_sq_ft=maximum,
            waterproof_required=(
                self.waterproof_required
                if incoming.waterproof_required is None
                else incoming.waterproof_required
            ),
            has_pets=self.has_pets if incoming.has_pets is None else incoming.has_pets,
            has_kids=self.has_kids if incoming.has_kids is None else incoming.has_kids,
            traffic_level=incoming.traffic_level or self.traffic_level,
            usage=incoming.usage or self.usage,
            unmapped_catalog_terms=unmapped,
        )

    def to_search_filters(self) -> SearchFilters:
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

    def semantic_query(self) -> str:
        """Build retrieval text from validated preferences, not raw instructions."""

        parts: list[str] = []
        labelled = (
            ("flooring type", self.product_types),
            ("room", self.rooms),
            ("material", self.materials),
            ("color", self.colors),
            ("shade", self.shades),
            ("style", self.styles),
            ("brand", self.brands),
            ("installation", self.installation_preferences),
            ("durability", self.durability_requirements),
            ("appearance", self.semantic_preferences),
        )
        for label, values in labelled:
            if values:
                parts.append(f"{label}: {', '.join(values)}")
        if self.waterproof_required is not None:
            parts.append(f"waterproof: {'yes' if self.waterproof_required else 'no'}")
        if self.has_pets is not None:
            parts.append(f"pets: {'yes' if self.has_pets else 'no'}")
        if self.has_kids is not None:
            parts.append(f"kids: {'yes' if self.has_kids else 'no'}")
        if self.traffic_level:
            parts.append(f"traffic: {self.traffic_level.value}")
        if self.usage:
            parts.append(f"usage: {self.usage.value}")
        return "; ".join(parts)


class ClarificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field: str
    question: str


class AgentRankedCandidate(BaseModel):
    """Step 6 ranking output without the Step 7 presentation-card fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sku: str
    score: RankingScore


class AgentTurnResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: AgentAction
    message: str
    clarification_field: str | None = None
    preferences: ConversationPreferences
    candidate_skus: tuple[str, ...] = ()
    ranked_candidates: tuple[AgentRankedCandidate, ...] = ()
    recommendations: tuple[RecommendationCard, ...] = ()
