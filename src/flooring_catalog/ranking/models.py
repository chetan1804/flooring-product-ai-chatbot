"""Models for explainable, configurable recommendation ranking."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from flooring_catalog.search.models import HybridCandidate


class ScoreComponentName(StrEnum):
    RETRIEVAL = "retrieval"
    ROOM_SUITABILITY = "room_suitability"
    LIFESTYLE = "lifestyle"
    BUDGET_FIT = "budget_fit"
    AVAILABILITY = "availability"


class ScoreComponent(BaseModel):
    """One normalized and inspectable contribution to a ranking score."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: ScoreComponentName
    raw_score: float = Field(ge=0, le=1)
    weight: float = Field(ge=0, le=1)
    contribution: float = Field(ge=0, le=1)
    reasons: tuple[str, ...] = ()


class RankingScore(BaseModel):
    """Final score plus the exact components used to calculate it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total: float = Field(ge=0, le=1)
    components: tuple[ScoreComponent, ...]


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    candidate: HybridCandidate
    score: RankingScore


@dataclass(frozen=True, slots=True)
class RankingWeights:
    retrieval: float = 0.40
    room_suitability: float = 0.20
    lifestyle: float = 0.15
    budget_fit: float = 0.15
    availability: float = 0.10

    def __post_init__(self) -> None:
        values = self.as_dict().values()
        if any(weight < 0 for weight in values):
            raise ValueError("ranking weights cannot be negative")
        if sum(values) <= 0:
            raise ValueError("at least one ranking weight must be positive")

    def as_dict(self) -> dict[ScoreComponentName, float]:
        return {
            ScoreComponentName.RETRIEVAL: self.retrieval,
            ScoreComponentName.ROOM_SUITABILITY: self.room_suitability,
            ScoreComponentName.LIFESTYLE: self.lifestyle,
            ScoreComponentName.BUDGET_FIT: self.budget_fit,
            ScoreComponentName.AVAILABILITY: self.availability,
        }


@dataclass(frozen=True, slots=True)
class RankingConfig:
    weights: RankingWeights = field(default_factory=RankingWeights)
    result_limit: int = 5

    def __post_init__(self) -> None:
        if not 1 <= self.result_limit <= 20:
            raise ValueError("result_limit must be between 1 and 20")
