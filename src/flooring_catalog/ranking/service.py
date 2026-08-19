"""Explainable deterministic scoring and top-product selection."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from flooring_catalog.ranking.models import (
    RankedCandidate,
    RankingConfig,
    RankingScore,
    ScoreComponent,
    ScoreComponentName,
)
from flooring_catalog.ranking.rules import FlooringBusinessRules, PreferenceFacts, RuleAssessment
from flooring_catalog.search.models import HybridCandidate, SearchProduct


class RankingPreferences(PreferenceFacts, Protocol):
    budget_min_per_sq_ft: Decimal | None
    budget_max_per_sq_ft: Decimal | None


def _clamp(score: float) -> float:
    return max(0.0, min(1.0, score))


class FlooringRecommendationRanker:
    """Combine retrieval relevance and business rules using configurable weights."""

    def __init__(
        self,
        rules: FlooringBusinessRules | None = None,
        config: RankingConfig | None = None,
    ) -> None:
        self._rules = rules or FlooringBusinessRules()
        self._config = config or RankingConfig()

    def rank(
        self,
        candidates: list[HybridCandidate],
        preferences: RankingPreferences,
    ) -> list[RankedCandidate]:
        ranked = [self._score(candidate, preferences) for candidate in candidates]
        ranked.sort(
            key=lambda item: (
                -item.score.total,
                -item.candidate.retrieval_score,
                item.candidate.product.sku,
            )
        )
        return ranked[: self._config.result_limit]

    def _score(
        self, candidate: HybridCandidate, preferences: RankingPreferences
    ) -> RankedCandidate:
        product = candidate.product
        assessments = {
            ScoreComponentName.RETRIEVAL: RuleAssessment(
                _clamp(candidate.retrieval_score),
                (
                    "Hybrid retrieval score combines validated structured filters "
                    "and semantic similarity.",
                ),
            ),
            ScoreComponentName.ROOM_SUITABILITY: self._rules.room_suitability(
                product, preferences
            ),
            ScoreComponentName.LIFESTYLE: self._rules.lifestyle_suitability(
                product, preferences
            ),
            ScoreComponentName.BUDGET_FIT: self._budget_fit(product, preferences),
            ScoreComponentName.AVAILABILITY: self._availability(product),
        }
        configured_weights = self._config.weights.as_dict()
        total_weight = sum(configured_weights.values())
        components: list[ScoreComponent] = []
        for name, assessment in assessments.items():
            normalized_weight = configured_weights[name] / total_weight
            raw_score = _clamp(assessment.score)
            components.append(
                ScoreComponent(
                    name=name,
                    raw_score=round(raw_score, 6),
                    weight=round(normalized_weight, 6),
                    contribution=round(raw_score * normalized_weight, 6),
                    reasons=assessment.reasons,
                )
            )
        total = round(sum(component.contribution for component in components), 6)
        return RankedCandidate(
            candidate=candidate,
            score=RankingScore(total=min(1.0, total), components=tuple(components)),
        )

    @staticmethod
    def _budget_fit(
        product: SearchProduct, preferences: RankingPreferences
    ) -> RuleAssessment:
        minimum = preferences.budget_min_per_sq_ft
        maximum = preferences.budget_max_per_sq_ft
        if minimum is None and maximum is None:
            return RuleAssessment(0.5, ("No budget preference was supplied.",))
        if product.price is None:
            return RuleAssessment(
                0.5,
                ("Catalog price is unavailable, so budget fit remains neutral.",),
            )
        if minimum is not None and product.price < minimum:
            return RuleAssessment(0.0, ("Catalog price is below the requested range.",))
        if maximum is not None and product.price > maximum:
            return RuleAssessment(0.0, ("Catalog price exceeds the requested budget.",))
        return RuleAssessment(1.0, ("Catalog price is within the requested budget.",))

    @staticmethod
    def _availability(product: SearchProduct) -> RuleAssessment:
        value = product.metadata.get("in_stock")
        if isinstance(value, bool):
            in_stock = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            in_stock = value > 0
        elif isinstance(value, str):
            normalized = value.strip().casefold()
            in_stock = normalized in {"yes", "true", "in stock"} if normalized else None
        else:
            in_stock = None
        if in_stock is True:
            return RuleAssessment(1.0, ("Catalog inventory indicates the product is in stock.",))
        if in_stock is False:
            return RuleAssessment(0.25, ("Catalog inventory does not indicate available stock.",))
        return RuleAssessment(0.5, ("Catalog inventory status is unavailable.",))
