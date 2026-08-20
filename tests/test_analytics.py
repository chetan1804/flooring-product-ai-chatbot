from __future__ import annotations

from uuid import UUID

import pytest

from flooring_catalog.analytics import (
    AnalyticsEvent,
    AnalyticsEventType,
    FeedbackRating,
    InMemoryAnalyticsStore,
    RecommendationFeedback,
)

SESSION_ID = UUID("85d60cba-e03a-4f34-b285-ff4841e004f7")
INTERACTION_ID = UUID("d24d7537-d249-4b00-9690-1c11676a4052")


def test_feedback_requires_a_matching_completed_interaction() -> None:
    store = InMemoryAnalyticsStore()
    feedback = RecommendationFeedback(
        site_code="CLIENT001",
        session_id=SESSION_ID,
        interaction_id=INTERACTION_ID,
        rating=FeedbackRating.HELPFUL,
    )
    with pytest.raises(ValueError, match="Unknown recommendation interaction"):
        store.submit_feedback(feedback)

    store.record(
        AnalyticsEvent(
            site_code="CLIENT001",
            session_id=SESSION_ID,
            interaction_id=INTERACTION_ID,
            event_type=AnalyticsEventType.CHAT_COMPLETED,
            action="candidates",
            recommendation_count=5,
        )
    )
    store.submit_feedback(feedback)
    assert store.feedback == [feedback]


def test_analytics_event_contains_no_customer_message_field() -> None:
    assert "message" not in AnalyticsEvent.__dataclass_fields__
    assert "message" not in RecommendationFeedback.__dataclass_fields__
