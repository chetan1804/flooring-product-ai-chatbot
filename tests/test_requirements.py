from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from psycopg.rows import tuple_row
from pydantic import ValidationError

from flooring_catalog.requirements.mapper import CatalogRequirementMapper
from flooring_catalog.requirements.models import (
    CatalogVocabulary,
    CustomerRequirements,
    TrafficLevel,
    UsageType,
)
from flooring_catalog.requirements.provider import (
    OpenAIRequirementExtractor,
    RequirementExtractionSettings,
)
from flooring_catalog.requirements.service import RequirementExtractionService
from flooring_catalog.requirements.vocabulary import CatalogVocabularyRepository


def test_customer_requirements_normalize_blank_and_duplicate_lists() -> None:
    requirements = CustomerRequirements(
        colors=[" Light Oak ", "light oak", "  "],
        rooms=["Kitchen"],
        traffic_level="high",
        usage="residential",
    )
    assert requirements.colors == ["Light Oak"]
    assert requirements.rooms == ["Kitchen"]
    assert requirements.traffic_level is TrafficLevel.HIGH
    assert requirements.usage is UsageType.RESIDENTIAL


def test_customer_requirements_forbid_unknown_model_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        CustomerRequirements.model_validate({"sql": "DROP TABLE catalog_products"})


def test_customer_requirements_validate_budget_range() -> None:
    with pytest.raises(ValidationError, match="budget minimum cannot exceed"):
        CustomerRequirements(budget_min_per_sq_ft=8, budget_max_per_sq_ft=4)
    with pytest.raises(ValidationError):
        CustomerRequirements(budget_max_per_sq_ft=-1)


@pytest.fixture
def vocabulary() -> CatalogVocabulary:
    return CatalogVocabulary(
        product_types=("carpet", "hardwood", "laminate", "lvt", "tile"),
        brands=("Shaw Floors", "Mohawk"),
        materials=("Ceramic", "Nylon"),
        colors=("Light Oak", "Warm Beige"),
        styles=("Modern", "Loop/Berber"),
    )


def test_mapper_converts_language_to_real_catalog_values(
    vocabulary: CatalogVocabulary,
) -> None:
    requirements = CustomerRequirements(
        product_types=["Luxury vinyl"],
        rooms=["kitchen"],
        materials=["ceramic", "bamboo"],
        colors=["light oak"],
        styles=["modern"],
        brands=["shaw floors"],
        budget_max_per_sq_ft=6.5,
        waterproof_required=True,
        has_pets=True,
        semantic_preferences=["warm", "natural looking"],
    )
    normalized = CatalogRequirementMapper(vocabulary).normalize(
        requirements,
        customer_message="I need warm natural luxury vinyl for my kitchen under $6.50/sq ft.",
    )
    assert normalized.product_types == ("lvt",)
    assert normalized.brands == ("Shaw Floors",)
    assert normalized.materials == ("Ceramic",)
    assert normalized.colors == ("Light Oak",)
    assert normalized.styles == ("Modern",)
    assert normalized.unmapped_catalog_terms == {"materials": ("bamboo",)}
    filters = normalized.to_search_filters()
    assert filters.z_prod_types == ("lvt",)
    assert filters.maximum_price is not None
    assert str(filters.maximum_price) == "6.5"
    assert filters.waterproof is True
    assert normalized.semantic_query.startswith("I need warm natural")


def test_product_alias_is_not_accepted_when_target_is_absent() -> None:
    vocabulary = CatalogVocabulary(product_types=("tile",))
    requirements = CustomerRequirements(product_types=["luxury vinyl"])
    normalized = CatalogRequirementMapper(vocabulary).normalize(
        requirements, customer_message="luxury vinyl"
    )
    assert normalized.product_types == ()
    assert normalized.unmapped_catalog_terms == {
        "product_types": ("luxury vinyl",)
    }


def test_untrusted_extracted_values_never_become_catalog_filters(
    vocabulary: CatalogVocabulary,
) -> None:
    attack = "lvt'); DROP TABLE catalog_products; --"
    normalized = CatalogRequirementMapper(vocabulary).normalize(
        CustomerRequirements(product_types=[attack]), customer_message=attack
    )
    assert normalized.to_search_filters().z_prod_types == ()
    assert normalized.unmapped_catalog_terms["product_types"] == (attack,)


def test_extraction_settings_are_environment_driven() -> None:
    assert RequirementExtractionSettings.from_env({}).model == "gpt-5-mini"
    assert RequirementExtractionSettings.from_env(
        {"REQUIREMENT_EXTRACTION_MODEL": "custom-model"}
    ).model == "custom-model"
    with pytest.raises(ValueError, match="cannot be empty"):
        RequirementExtractionSettings.from_env({"REQUIREMENT_EXTRACTION_MODEL": " "})


class FakeResponses:
    def __init__(self, parsed: CustomerRequirements | None) -> None:
        self.parsed = parsed
        self.arguments: dict[str, Any] = {}

    def parse(self, **kwargs: Any) -> Any:
        self.arguments = kwargs
        return SimpleNamespace(output_parsed=self.parsed)


def test_openai_extractor_uses_pydantic_structured_output_and_catalog_types() -> None:
    responses = FakeResponses(CustomerRequirements(product_types=["lvt"], rooms=["kitchen"]))
    client = SimpleNamespace(responses=responses)
    extractor = OpenAIRequirementExtractor(
        RequirementExtractionSettings(model="test-model"), client=client  # type: ignore[arg-type]
    )
    result = extractor.extract("I need LVT for a kitchen", ["tile", "lvt"])
    assert result.product_types == ["lvt"]
    assert responses.arguments["model"] == "test-model"
    assert responses.arguments["text_format"] is CustomerRequirements
    messages = responses.arguments["input"]
    assert messages[0]["role"] == "system"
    assert '["lvt", "tile"]' in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "I need LVT for a kitchen"}


def test_openai_extractor_rejects_missing_parsed_output() -> None:
    client = SimpleNamespace(responses=FakeResponses(None))
    extractor = OpenAIRequirementExtractor(
        RequirementExtractionSettings(), client=client  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError, match="no parsed output"):
        extractor.extract("flooring", ["lvt"])


class FakeExtractor:
    model = "fake"

    def __init__(self) -> None:
        self.catalog_types: tuple[str, ...] = ()

    def extract(
        self, customer_message: str, catalog_product_types: tuple[str, ...]
    ) -> CustomerRequirements:
        assert customer_message == "Light oak vinyl for my kitchen"
        self.catalog_types = catalog_product_types
        return CustomerRequirements(
            product_types=["vinyl plank"], colors=["light oak"], rooms=["kitchen"]
        )


def test_service_combines_extraction_and_deterministic_mapping(
    vocabulary: CatalogVocabulary,
) -> None:
    extractor = FakeExtractor()
    result = RequirementExtractionService(extractor, vocabulary).extract(
        " Light oak vinyl for my kitchen "
    )
    assert extractor.catalog_types == vocabulary.product_types
    assert result.normalized.product_types == ("lvt",)
    assert result.normalized.colors == ("Light Oak",)
    assert result.normalized.rooms == ("kitchen",)


class FakeVocabularyCursor:
    def __init__(self, values: dict[str, list[str]]) -> None:
        self.values = values
        self.current_column = ""

    def __enter__(self) -> FakeVocabularyCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str) -> None:
        for column in ("z_prod_type", "brand", "material", "color", "style"):
            if f"btrim({column})" in statement:
                self.current_column = column
                return
        raise AssertionError("unexpected vocabulary SQL")

    def fetchall(self) -> list[tuple[str]]:
        return [(value,) for value in self.values[self.current_column]]


class FakeVocabularyConnection:
    def __init__(self) -> None:
        self.requested_row_factory: object | None = None

    def cursor(self, *, row_factory: object | None = None) -> FakeVocabularyCursor:
        self.requested_row_factory = row_factory
        return FakeVocabularyCursor(
            {
                "z_prod_type": ["lvt", "tile"],
                "brand": ["Shaw Floors"],
                "material": ["Ceramic"],
                "color": ["Light Oak"],
                "style": ["Modern"],
            }
        )


def test_vocabulary_is_loaded_from_database_values() -> None:
    connection = FakeVocabularyConnection()
    vocabulary = CatalogVocabularyRepository(connection).load()  # type: ignore[arg-type]
    assert vocabulary.product_types == ("lvt", "tile")
    assert vocabulary.brands == ("Shaw Floors",)
    assert vocabulary.colors == ("Light Oak",)
    assert connection.requested_row_factory is tuple_row
