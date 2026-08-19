"""AI-assisted customer requirement extraction and catalog normalization."""

from flooring_catalog.requirements.mapper import CatalogRequirementMapper
from flooring_catalog.requirements.models import (
    CatalogVocabulary,
    CustomerRequirements,
    NormalizedRequirements,
    RequirementExtractionResult,
)
from flooring_catalog.requirements.provider import (
    OpenAIRequirementExtractor,
    RequirementExtractionSettings,
)
from flooring_catalog.requirements.service import RequirementExtractionService

__all__ = [
    "CatalogRequirementMapper",
    "CatalogVocabulary",
    "CustomerRequirements",
    "NormalizedRequirements",
    "OpenAIRequirementExtractor",
    "RequirementExtractionResult",
    "RequirementExtractionService",
    "RequirementExtractionSettings",
]

