from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from flooring_catalog.agent.models import ConversationPreferences
from flooring_catalog.ranking import (
    FlooringRecommendationRanker,
    RankingConfig,
    RankingWeights,
)
from flooring_catalog.ranking.models import ScoreComponentName
from flooring_catalog.requirements.models import TrafficLevel, UsageType
from flooring_catalog.search.models import HybridCandidate, SearchProduct


def candidate(
    sku: str,
    *,
    retrieval_score: float = 0.8,
    product_type: str = "lvt",
    waterproof: str | None = "Yes",
    price: Decimal | None = None,
    metadata: dict[str, Any] | None = None,
) -> HybridCandidate:
    product = SearchProduct(
        sku=sku,
        name=f"Product {sku}",
        z_prod_type=product_type,
        swatch="image.jpg",
        price=price,
        brand=None,
        material=None,
        color=None,
        style=None,
        description=None,
        gallery_images=None,
        waterproof=waterproof,
        metadata=metadata or {},
        semantic_similarity=retrieval_score,
    )
    return HybridCandidate(
        product=product,
        structured_match=True,
        semantic_similarity=retrieval_score,
        retrieval_score=retrieval_score,
    )


def component(ranked: Any, name: ScoreComponentName) -> Any:
    return next(item for item in ranked.score.components if item.name is name)


def test_bathroom_rule_prioritizes_catalog_waterproof_product() -> None:
    ranker = FlooringRecommendationRanker()
    ranked = ranker.rank(
        [
            candidate("DRY", waterproof="No"),
            candidate("WET", waterproof="Yes"),
        ],
        ConversationPreferences(rooms=("bathroom",)),
    )
    assert [item.candidate.product.sku for item in ranked] == ["WET", "DRY"]
    wet_room = component(ranked[0], ScoreComponentName.ROOM_SUITABILITY)
    dry_room = component(ranked[1], ScoreComponentName.ROOM_SUITABILITY)
    assert wet_room.raw_score == 1
    assert dry_room.raw_score == 0.1
    assert "waterproof" in wet_room.reasons[0]


def test_lifestyle_rules_use_confirmed_catalog_metadata() -> None:
    ranker = FlooringRecommendationRanker()
    ranked = ranker.rank(
        [
            candidate(
                "RESIDENTIAL",
                product_type="carpet",
                metadata={"application": "Residential"},
            ),
            candidate(
                "COMMERCIAL",
                metadata={
                    "application": "Commercial",
                    "features": ["Scratch Resistant", "Stain Resistant"],
                    "wear_layer": "20 mil",
                },
            ),
        ],
        ConversationPreferences(
            rooms=("office",),
            has_pets=True,
            traffic_level=TrafficLevel.HIGH,
            usage=UsageType.COMMERCIAL,
        ),
    )
    assert ranked[0].candidate.product.sku == "COMMERCIAL"
    lifestyle = component(ranked[0], ScoreComponentName.LIFESTYLE)
    assert lifestyle.raw_score == 1
    assert any("Commercial" in reason for reason in lifestyle.reasons)


def test_missing_price_is_neutral_and_never_treated_as_zero() -> None:
    ranker = FlooringRecommendationRanker()
    ranked = ranker.rank(
        [candidate("UNKNOWN", price=None), candidate("IN-BUDGET", price=Decimal("4.50"))],
        ConversationPreferences(
            rooms=("office",),
            budget_max_per_sq_ft=Decimal("5"),
        ),
    )
    by_sku = {item.candidate.product.sku: item for item in ranked}
    unknown = component(by_sku["UNKNOWN"], ScoreComponentName.BUDGET_FIT)
    in_budget = component(by_sku["IN-BUDGET"], ScoreComponentName.BUDGET_FIT)
    assert unknown.raw_score == 0.5
    assert "unavailable" in unknown.reasons[0]
    assert in_budget.raw_score == 1


def test_configurable_weights_change_ranking_priority() -> None:
    candidates = [
        candidate("RELEVANT", retrieval_score=0.95, waterproof="No"),
        candidate("SUITABLE", retrieval_score=0.40, waterproof="Yes"),
    ]
    preferences = ConversationPreferences(rooms=("bathroom",))
    retrieval_only = FlooringRecommendationRanker(
        config=RankingConfig(
            weights=RankingWeights(
                retrieval=1,
                room_suitability=0,
                lifestyle=0,
                budget_fit=0,
                availability=0,
            )
        )
    )
    room_only = FlooringRecommendationRanker(
        config=RankingConfig(
            weights=RankingWeights(
                retrieval=0,
                room_suitability=1,
                lifestyle=0,
                budget_fit=0,
                availability=0,
            )
        )
    )
    assert retrieval_only.rank(candidates, preferences)[0].candidate.product.sku == "RELEVANT"
    assert room_only.rank(candidates, preferences)[0].candidate.product.sku == "SUITABLE"


def test_ranker_selects_top_n_deterministically_with_explainable_components() -> None:
    ranker = FlooringRecommendationRanker(config=RankingConfig(result_limit=2))
    ranked = ranker.rank(
        [candidate("C"), candidate("A"), candidate("B")],
        ConversationPreferences(rooms=("office",)),
    )
    assert [item.candidate.product.sku for item in ranked] == ["A", "B"]
    assert len(ranked[0].score.components) == len(ScoreComponentName)
    assert ranked[0].score.total == pytest.approx(
        sum(item.contribution for item in ranked[0].score.components)
    )


def test_ranking_configuration_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="positive"):
        RankingWeights(
            retrieval=0,
            room_suitability=0,
            lifestyle=0,
            budget_fit=0,
            availability=0,
        )
    with pytest.raises(ValueError, match="between 1 and 20"):
        RankingConfig(result_limit=21)
