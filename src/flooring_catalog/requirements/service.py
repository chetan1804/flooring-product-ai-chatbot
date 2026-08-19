"""Orchestrate structured extraction and deterministic catalog normalization."""

from __future__ import annotations

from flooring_catalog.requirements.mapper import CatalogRequirementMapper
from flooring_catalog.requirements.models import CatalogVocabulary, RequirementExtractionResult
from flooring_catalog.requirements.provider import RequirementExtractor


class RequirementExtractionService:
    def __init__(
        self,
        extractor: RequirementExtractor,
        vocabulary: CatalogVocabulary,
    ) -> None:
        self._extractor = extractor
        self._vocabulary = vocabulary
        self._mapper = CatalogRequirementMapper(vocabulary)

    def extract(self, customer_message: str) -> RequirementExtractionResult:
        message = customer_message.strip()
        if not message:
            raise ValueError("customer_message cannot be empty")
        extracted = self._extractor.extract(message, self._vocabulary.product_types)
        normalized = self._mapper.normalize(extracted, customer_message=message)
        return RequirementExtractionResult(extracted=extracted, normalized=normalized)

