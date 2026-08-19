from __future__ import annotations

from typing import Any

import pytest

from flooring_catalog.agent import FlooringConversationAgent, build_flooring_agent_graph
from flooring_catalog.agent.clarification import MissingInformationDetector
from flooring_catalog.agent.models import AgentAction, ConversationPreferences
from flooring_catalog.recommendations import RecommendationCardService
from flooring_catalog.requirements.models import (
    CustomerRequirements,
    NormalizedRequirements,
    RequirementExtractionResult,
)
from flooring_catalog.search.models import HybridCandidate, SearchFilters, SearchProduct


def normalized(**values: Any) -> NormalizedRequirements:
    return NormalizedRequirements(semantic_query=values.pop("semantic_query", "message"), **values)


class FakeExtractionService:
    def __init__(self, results: dict[str, NormalizedRequirements]) -> None:
        self.results = results
        self.messages: list[str] = []

    def extract(self, customer_message: str) -> RequirementExtractionResult:
        self.messages.append(customer_message)
        return RequirementExtractionResult(
            extracted=CustomerRequirements(),
            normalized=self.results[customer_message],
        )


def product(sku: str) -> SearchProduct:
    return SearchProduct(
        sku=sku,
        name=f"Product {sku}",
        z_prod_type="lvt",
        swatch="image.jpg",
        price=None,
        brand=None,
        material=None,
        color="Light Oak",
        style=None,
        description=None,
        gallery_images=None,
        waterproof="Yes",
        metadata={},
    )


class FakeSearchService:
    def __init__(self, skus: tuple[str, ...] = ("SKU-1", "SKU-2")) -> None:
        self.skus = skus
        self.calls: list[tuple[str | None, SearchFilters]] = []

    def search(self, *, query: str | None, filters: SearchFilters) -> list[HybridCandidate]:
        self.calls.append((query, filters))
        return [
            HybridCandidate(
                product=product(sku),
                structured_match=True,
                semantic_similarity=0.8,
                retrieval_score=0.88,
            )
            for sku in self.skus
        ]


def test_preference_merge_preserves_prior_values_and_overwrites_scalars() -> None:
    first = ConversationPreferences().merge(
        normalized(rooms=("kitchen",), has_pets=True, waterproof_required=False)
    )
    second = first.merge(
        normalized(product_types=("lvt",), colors=("Light Oak",), waterproof_required=True)
    )
    assert second.rooms == ("kitchen",)
    assert second.product_types == ("lvt",)
    assert second.colors == ("Light Oak",)
    assert second.has_pets is True
    assert second.waterproof_required is True


def test_detector_uses_dynamic_product_types_and_asks_one_material_question() -> None:
    detector = MissingInformationDetector(("carpet", "lvt", "tile"))
    request = detector.detect(ConversationPreferences())
    assert request is not None
    assert request.field == "product_type"
    assert "carpet, lvt, tile" in request.question

    request = detector.detect(ConversationPreferences(product_types=("lvt",)))
    assert request is not None
    assert request.field == "room"


def test_unmapped_product_type_gets_catalog_specific_clarification() -> None:
    detector = MissingInformationDetector(("lvt", "tile"))
    request = detector.detect(
        ConversationPreferences(
            unmapped_catalog_terms={"product_types": ("cork",)}
        )
    )
    assert request is not None
    assert request.field == "product_type"
    assert "cork" in request.question
    assert "lvt, tile" in request.question


def test_graph_remembers_preferences_and_does_not_repeat_questions() -> None:
    extraction = FakeExtractionService(
        {
            "I need flooring for my kitchen": normalized(rooms=("kitchen",)),
            "Luxury vinyl": normalized(product_types=("lvt",)),
            "Light oak": normalized(colors=("Light Oak",)),
        }
    )
    search = FakeSearchService()
    agent = FlooringConversationAgent(
        build_flooring_agent_graph(
            extraction,  # type: ignore[arg-type]
            search,
            ("carpet", "hardwood", "laminate", "lvt", "tile"),
            recommendation_service=RecommendationCardService("https://shop.example"),
        )
    )

    first = agent.respond(
        thread_id="customer-1", user_message="I need flooring for my kitchen"
    )
    assert first.action is AgentAction.CLARIFY
    assert first.clarification_field == "product_type"
    assert first.preferences.rooms == ("kitchen",)
    assert search.calls == []

    second = agent.respond(thread_id="customer-1", user_message="Luxury vinyl")
    assert second.action is AgentAction.CLARIFY
    assert second.clarification_field == "appearance"
    assert second.preferences.rooms == ("kitchen",)
    assert second.preferences.product_types == ("lvt",)

    third = agent.respond(thread_id="customer-1", user_message="Light oak")
    assert third.action is AgentAction.CANDIDATES
    assert third.clarification_field is None
    assert third.preferences.rooms == ("kitchen",)
    assert third.preferences.product_types == ("lvt",)
    assert third.preferences.colors == ("Light Oak",)
    assert third.candidate_skus == ("SKU-1", "SKU-2")
    assert [candidate.sku for candidate in third.ranked_candidates] == ["SKU-1", "SKU-2"]
    assert all(candidate.score.components for candidate in third.ranked_candidates)
    assert [card.sku for card in third.recommendations] == ["SKU-1", "SKU-2"]
    assert third.recommendations[0].product_url == "https://shop.example/?s=SKU-1"
    assert len(search.calls) == 1
    query, filters = search.calls[0]
    assert query == "flooring type: lvt; room: kitchen; color: Light Oak"
    assert filters.z_prod_types == ("lvt",)
    assert filters.colors == ("light oak",)

    history = agent.history(thread_id="customer-1")
    assert [message.role.value for message in history] == [
        "user", "assistant", "user", "assistant", "user", "assistant"
    ]


def test_checkpointer_isolates_conversation_threads() -> None:
    extraction = FakeExtractionService(
        {
            "Kitchen": normalized(rooms=("kitchen",)),
            "Light oak": normalized(colors=("Light Oak",)),
        }
    )
    agent = FlooringConversationAgent(
        build_flooring_agent_graph(
            extraction,  # type: ignore[arg-type]
            FakeSearchService(),
            ("lvt", "tile"),
            recommendation_service=RecommendationCardService("https://shop.example"),
        )
    )
    agent.respond(thread_id="thread-a", user_message="Kitchen")
    other = agent.respond(thread_id="thread-b", user_message="Light oak")
    assert other.preferences.rooms == ()
    assert other.preferences.colors == ("Light Oak",)
    assert other.clarification_field == "product_type"


def test_graph_does_not_repeat_a_declined_clarification() -> None:
    extraction = FakeExtractionService(
        {
            "LVT for my kitchen": normalized(
                product_types=("lvt",), rooms=("kitchen",)
            ),
            "No preference": normalized(),
        }
    )
    search = FakeSearchService()
    agent = FlooringConversationAgent(
        build_flooring_agent_graph(
            extraction,  # type: ignore[arg-type]
            search,
            ("lvt", "tile"),
            recommendation_service=RecommendationCardService("https://shop.example"),
        )
    )
    first = agent.respond(thread_id="declined", user_message="LVT for my kitchen")
    assert first.clarification_field == "appearance"

    second = agent.respond(thread_id="declined", user_message="No preference")
    assert second.action is AgentAction.CANDIDATES
    assert second.clarification_field is None
    assert len(search.calls) == 1


def test_no_results_are_returned_without_inventing_products() -> None:
    extraction = FakeExtractionService(
        {
            "Complete": normalized(
                product_types=("lvt",), rooms=("kitchen",), colors=("Light Oak",)
            )
        }
    )
    agent = FlooringConversationAgent(
        build_flooring_agent_graph(
            extraction,  # type: ignore[arg-type]
            FakeSearchService(skus=()),
            ("lvt",),
            recommendation_service=RecommendationCardService("https://shop.example"),
        )
    )
    result = agent.respond(thread_id="none", user_message="Complete")
    assert result.action is AgentAction.NO_RESULTS
    assert result.candidate_skus == ()
    assert "couldn't find" in result.message


@pytest.mark.parametrize(("thread_id", "message"), [("", "hello"), ("x", " ")])
def test_agent_validates_invocation(thread_id: str, message: str) -> None:
    agent = FlooringConversationAgent(
        build_flooring_agent_graph(
            FakeExtractionService({}),  # type: ignore[arg-type]
            FakeSearchService(),
            ("lvt",),
            recommendation_service=RecommendationCardService("https://shop.example"),
        )
    )
    with pytest.raises(ValueError):
        agent.respond(thread_id=thread_id, user_message=message)
