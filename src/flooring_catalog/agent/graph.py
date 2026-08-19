"""LangGraph workflow for multi-turn flooring candidate retrieval."""

from __future__ import annotations

from collections.abc import Sequence
from operator import add
from typing import Annotated, Any, Protocol, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from flooring_catalog.agent.clarification import MissingInformationDetector
from flooring_catalog.agent.models import (
    AgentAction,
    AgentRankedCandidate,
    AgentTurnResult,
    ChatMessage,
    ChatRole,
    ClarificationRequest,
    ConversationPreferences,
)
from flooring_catalog.ranking import FlooringRecommendationRanker, RankedCandidate
from flooring_catalog.requirements.models import NormalizedRequirements
from flooring_catalog.requirements.service import RequirementExtractionService
from flooring_catalog.search.models import HybridCandidate, SearchFilters


class CandidateSearchService(Protocol):
    def search(self, *, query: str | None, filters: SearchFilters) -> list[HybridCandidate]:
        """Return hybrid candidates for validated preferences."""


class CandidateRankingService(Protocol):
    def rank(
        self,
        candidates: list[HybridCandidate],
        preferences: ConversationPreferences,
    ) -> list[RankedCandidate]:
        """Return the best candidates in deterministic ranking order."""


class FlooringAgentState(TypedDict, total=False):
    user_message: str
    messages: Annotated[list[dict[str, str]], add]
    asked_clarification_fields: Annotated[list[str], add]
    latest_requirements: dict[str, Any]
    preferences: dict[str, Any]
    clarification: dict[str, str] | None
    action: str
    assistant_message: str
    candidate_skus: list[str]
    ranked_candidates: list[dict[str, Any]]
    search_query: str


def build_flooring_agent_graph(
    extraction_service: RequirementExtractionService,
    search_service: CandidateSearchService,
    catalog_product_types: tuple[str, ...],
    *,
    ranking_service: CandidateRankingService | None = None,
    checkpointer: Any | None = None,
) -> Any:
    """Compile the dependency-injected conversational graph."""

    detector = MissingInformationDetector(catalog_product_types)
    ranker = ranking_service or FlooringRecommendationRanker()

    def extract_requirements(state: FlooringAgentState) -> dict[str, Any]:
        message = state["user_message"].strip()
        result = extraction_service.extract(message)
        return {
            "messages": [ChatMessage(role=ChatRole.USER, content=message).model_dump(mode="json")],
            "latest_requirements": result.normalized.model_dump(mode="json"),
            "candidate_skus": [],
            "ranked_candidates": [],
        }

    def merge_preferences(state: FlooringAgentState) -> dict[str, Any]:
        existing = ConversationPreferences.model_validate(state.get("preferences", {}))
        incoming = NormalizedRequirements.model_validate(state["latest_requirements"])
        merged = existing.merge(incoming)
        return {"preferences": merged.model_dump(mode="json")}

    def assess_requirements(state: FlooringAgentState) -> dict[str, Any]:
        preferences = ConversationPreferences.model_validate(state["preferences"])
        already_asked = frozenset(state.get("asked_clarification_fields", []))
        clarification = detector.detect(preferences, already_asked)
        return {
            "clarification": clarification.model_dump(mode="json") if clarification else None
        }

    def route_after_assessment(state: FlooringAgentState) -> str:
        return "clarify" if state.get("clarification") else "search"

    def clarify(state: FlooringAgentState) -> dict[str, Any]:
        clarification = ClarificationRequest.model_validate(state["clarification"])
        message = clarification.question
        return {
            "action": AgentAction.CLARIFY.value,
            "assistant_message": message,
            "messages": [
                ChatMessage(role=ChatRole.ASSISTANT, content=message).model_dump(mode="json")
            ],
            "asked_clarification_fields": [clarification.field],
        }

    def search_products(state: FlooringAgentState) -> dict[str, Any]:
        preferences = ConversationPreferences.model_validate(state["preferences"])
        query = preferences.semantic_query()
        candidates = search_service.search(
            query=query or None,
            filters=preferences.to_search_filters(),
        )
        ranked = ranker.rank(candidates, preferences)
        candidate_skus = [item.candidate.product.sku for item in ranked]
        ranked_candidates = [
            AgentRankedCandidate(
                sku=item.candidate.product.sku,
                score=item.score,
            ).model_dump(mode="json")
            for item in ranked
        ]
        if candidate_skus:
            action = AgentAction.CANDIDATES
            message = f"I ranked {len(candidate_skus)} matching products."
        else:
            action = AgentAction.NO_RESULTS
            message = "I couldn't find matching products for those preferences."
        return {
            "action": action.value,
            "assistant_message": message,
            "messages": [
                ChatMessage(role=ChatRole.ASSISTANT, content=message).model_dump(mode="json")
            ],
            "candidate_skus": candidate_skus,
            "ranked_candidates": ranked_candidates,
            "search_query": query,
        }

    builder = StateGraph(FlooringAgentState)
    builder.add_node("extract_requirements", extract_requirements)
    builder.add_node("merge_preferences", merge_preferences)
    builder.add_node("assess_requirements", assess_requirements)
    builder.add_node("clarify", clarify)
    builder.add_node("search_products", search_products)
    builder.add_edge(START, "extract_requirements")
    builder.add_edge("extract_requirements", "merge_preferences")
    builder.add_edge("merge_preferences", "assess_requirements")
    builder.add_conditional_edges(
        "assess_requirements",
        route_after_assessment,
        {"clarify": "clarify", "search": "search_products"},
    )
    builder.add_edge("clarify", END)
    builder.add_edge("search_products", END)
    return builder.compile(checkpointer=checkpointer or InMemorySaver())


class FlooringConversationAgent:
    """Small application boundary around a compiled LangGraph."""

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    def respond(self, *, thread_id: str, user_message: str) -> AgentTurnResult:
        normalized_thread_id = thread_id.strip()
        if not normalized_thread_id or len(normalized_thread_id) > 255:
            raise ValueError("thread_id must contain between 1 and 255 characters")
        if not user_message.strip():
            raise ValueError("user_message cannot be empty")
        config = {"configurable": {"thread_id": normalized_thread_id}}
        state = self._graph.invoke({"user_message": user_message}, config=config)
        clarification = state.get("clarification")
        return AgentTurnResult(
            action=state["action"],
            message=state["assistant_message"],
            clarification_field=clarification["field"] if clarification else None,
            preferences=ConversationPreferences.model_validate(state["preferences"]),
            candidate_skus=tuple(state.get("candidate_skus", [])),
            ranked_candidates=tuple(
                AgentRankedCandidate.model_validate(item)
                for item in state.get("ranked_candidates", [])
            ),
        )

    def history(self, *, thread_id: str) -> Sequence[ChatMessage]:
        config = {"configurable": {"thread_id": thread_id.strip()}}
        snapshot = self._graph.get_state(config)
        messages = snapshot.values.get("messages", [])
        return tuple(ChatMessage.model_validate(message) for message in messages)
