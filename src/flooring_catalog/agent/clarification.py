"""Deterministic missing-information policy, separate from model prompts."""

from __future__ import annotations

from flooring_catalog.agent.models import ClarificationRequest, ConversationPreferences


class MissingInformationDetector:
    """Ask at most one question when it materially narrows candidate retrieval."""

    def __init__(self, catalog_product_types: tuple[str, ...]) -> None:
        self._catalog_product_types = catalog_product_types

    def detect(
        self,
        preferences: ConversationPreferences,
        already_asked: frozenset[str] = frozenset(),
    ) -> ClarificationRequest | None:
        if not preferences.product_types and "product_type" not in already_asked:
            unmatched = preferences.unmapped_catalog_terms.get("product_types", ())
            available = ", ".join(self._catalog_product_types)
            if unmatched:
                return ClarificationRequest(
                    field="product_type",
                    question=(
                        f"I couldn't match '{unmatched[-1]}' to the catalog. "
                        f"Which type would you prefer: {available}?"
                    ),
                )
            return ClarificationRequest(
                field="product_type",
                question=f"What flooring type do you prefer? Available types: {available}.",
            )

        if (
            not preferences.rooms
            and preferences.usage is None
            and "room" not in already_asked
        ):
            return ClarificationRequest(
                field="room",
                question="Which room or area is this flooring for?",
            )

        appearance_known = any(
            (
                preferences.colors,
                preferences.shades,
                preferences.styles,
                preferences.materials,
                preferences.brands,
                preferences.semantic_preferences,
            )
        )
        if not appearance_known and "appearance" not in already_asked:
            return ClarificationRequest(
                field="appearance",
                question="Do you have a preferred color, shade, style, or overall look?",
            )
        return None
