"""Strict schemas for repeatable recommendation quality evaluations."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from flooring_catalog.agent.models import ConversationPreferences
from flooring_catalog.search.models import HybridCandidate, SearchProduct


class EvaluationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sku: str = Field(min_length=1)
    name: str | None = None
    product_type: str | None = None
    waterproof: str | None = None
    price: Decimal | None = Field(default=None, gt=0)
    brand: str | None = None
    material: str | None = None
    color: str | None = None
    style: str | None = None
    description: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    retrieval_score: float = Field(ge=0, le=1)
    structured_match: bool = True

    def to_hybrid_candidate(self) -> HybridCandidate:
        product = SearchProduct(
            sku=self.sku,
            name=self.name or self.sku,
            z_prod_type=self.product_type,
            swatch="evaluation-image.jpg",
            price=self.price,
            brand=self.brand,
            material=self.material,
            color=self.color,
            style=self.style,
            description=self.description,
            gallery_images=None,
            waterproof=self.waterproof,
            metadata=self.metadata,
            semantic_similarity=self.retrieval_score,
        )
        return HybridCandidate(
            product=product,
            structured_match=self.structured_match,
            semantic_similarity=self.retrieval_score,
            retrieval_score=self.retrieval_score,
        )


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    description: str = Field(min_length=1)
    preferences: ConversationPreferences
    candidates: tuple[EvaluationCandidate, ...] = Field(min_length=2)
    acceptable_top_skus: tuple[str, ...] = Field(min_length=1)
    required_skus: tuple[str, ...] = ()
    forbidden_skus: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_expected_skus(self) -> EvaluationCase:
        candidate_skus = {candidate.sku for candidate in self.candidates}
        expected = set(self.acceptable_top_skus) | set(self.required_skus) | set(
            self.forbidden_skus
        )
        unknown = expected - candidate_skus
        if unknown:
            raise ValueError(f"evaluation expectations reference unknown SKUs: {sorted(unknown)}")
        overlap = set(self.acceptable_top_skus) & set(self.forbidden_skus)
        if overlap:
            raise ValueError(f"SKUs cannot be both acceptable and forbidden: {sorted(overlap)}")
        return self


class EvaluationCorpus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    cases: tuple[EvaluationCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_case_ids(self) -> EvaluationCorpus:
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("evaluation case IDs must be unique")
        return self


class EvaluationCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    passed: bool
    details: str


class EvaluationCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    ranked_skus: tuple[str, ...]
    score: float = Field(ge=0, le=1)
    passed: bool
    checks: tuple[EvaluationCheck, ...]


class EvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    corpus_name: str
    corpus_version: str
    passed_cases: int = Field(ge=0)
    total_cases: int = Field(gt=0)
    pass_rate: float = Field(ge=0, le=1)
    mean_case_score: float = Field(ge=0, le=1)
    results: tuple[EvaluationCaseResult, ...]
