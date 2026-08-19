"""Response DTOs for customer-facing product recommendations."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from flooring_catalog.ranking.models import RankingScore


class RecommendationCard(BaseModel):
    """A clickable recommendation containing only catalog-derived product facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sku: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1)
    swatch: str = Field(min_length=1)
    image: str | None = None
    price: Decimal | None = Field(default=None, gt=0)
    attributes: dict[str, str] = Field(default_factory=dict)
    reasons: tuple[str, ...] = Field(min_length=1)
    product_url: str = Field(min_length=1)
    ranking: RankingScore
