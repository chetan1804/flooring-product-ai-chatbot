"""Catalog-backed recommendation cards and deterministic product links."""

from flooring_catalog.recommendations.models import RecommendationCard
from flooring_catalog.recommendations.service import RecommendationCardService
from flooring_catalog.recommendations.urls import (
    ClientDomainSettings,
    ProductUrlBuilder,
    normalize_http_origin,
)

__all__ = [
    "ClientDomainSettings",
    "ProductUrlBuilder",
    "RecommendationCard",
    "RecommendationCardService",
    "normalize_http_origin",
]
