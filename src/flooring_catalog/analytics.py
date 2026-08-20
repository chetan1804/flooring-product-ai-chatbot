"""Privacy-safe product analytics and structured recommendation feedback."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from threading import Lock
from uuid import UUID, uuid4

from psycopg_pool import ConnectionPool


class AnalyticsEventType(StrEnum):
    SESSION_CREATED = "session_created"
    WIDGET_OPENED = "widget_opened"
    CHAT_COMPLETED = "chat_completed"
    CHAT_FAILED = "chat_failed"
    PRODUCT_CLICKED = "product_clicked"


class FeedbackRating(StrEnum):
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"


class FeedbackReason(StrEnum):
    IRRELEVANT = "irrelevant"
    TOO_EXPENSIVE = "too_expensive"
    UNAVAILABLE = "unavailable"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class AnalyticsEvent:
    site_code: str
    session_id: UUID
    event_type: AnalyticsEventType
    interaction_id: UUID | None = None
    action: str | None = None
    recommendation_count: int | None = None
    sku: str | None = None
    event_id: UUID = field(default_factory=uuid4)


@dataclass(frozen=True, slots=True)
class RecommendationFeedback:
    site_code: str
    session_id: UUID
    interaction_id: UUID
    rating: FeedbackRating
    reason: FeedbackReason | None = None
    feedback_id: UUID = field(default_factory=uuid4)


class InMemoryAnalyticsStore:
    """Thread-safe analytics store for tests and local dependency injection."""

    def __init__(self) -> None:
        self.events: list[AnalyticsEvent] = []
        self.feedback: list[RecommendationFeedback] = []
        self._lock = Lock()

    def record(self, event: AnalyticsEvent) -> None:
        with self._lock:
            self.events.append(event)

    def submit_feedback(self, feedback: RecommendationFeedback) -> None:
        with self._lock:
            known_interaction = any(
                event.event_type is AnalyticsEventType.CHAT_COMPLETED
                and event.interaction_id == feedback.interaction_id
                and event.session_id == feedback.session_id
                and event.site_code == feedback.site_code
                for event in self.events
            )
            if not known_interaction:
                raise ValueError("Unknown recommendation interaction")
            self.feedback = [
                item
                for item in self.feedback
                if item.interaction_id != feedback.interaction_id
            ]
            self.feedback.append(feedback)


class PostgresAnalyticsStore:
    """PostgreSQL-backed analytics shared by all API replicas."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def record(self, event: AnalyticsEvent) -> None:
        with self._pool.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
INSERT INTO analytics_events (
    event_id, site_code, session_id, interaction_id, event_type,
    action, recommendation_count, sku
) VALUES (
    %(event_id)s, %(site_code)s, %(session_id)s, %(interaction_id)s, %(event_type)s,
    %(action)s, %(recommendation_count)s, %(sku)s
)
""",
                {
                    "event_id": event.event_id,
                    "site_code": event.site_code,
                    "session_id": event.session_id,
                    "interaction_id": event.interaction_id,
                    "event_type": event.event_type.value,
                    "action": event.action,
                    "recommendation_count": event.recommendation_count,
                    "sku": event.sku,
                },
            )

    def submit_feedback(self, feedback: RecommendationFeedback) -> None:
        with self._pool.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
INSERT INTO recommendation_feedback (
    feedback_id, site_code, session_id, interaction_id, rating, reason
)
SELECT %(feedback_id)s, %(site_code)s, %(session_id)s, %(interaction_id)s,
       %(rating)s, %(reason)s
FROM analytics_events
WHERE interaction_id = %(interaction_id)s
  AND session_id = %(session_id)s
  AND site_code = %(site_code)s
  AND event_type = 'chat_completed'
ON CONFLICT (interaction_id) DO UPDATE SET
    rating = EXCLUDED.rating,
    reason = EXCLUDED.reason,
    updated_at = now()
RETURNING feedback_id
""",
                {
                    "feedback_id": feedback.feedback_id,
                    "site_code": feedback.site_code,
                    "session_id": feedback.session_id,
                    "interaction_id": feedback.interaction_id,
                    "rating": feedback.rating.value,
                    "reason": feedback.reason.value if feedback.reason else None,
                },
            )
            if cursor.fetchone() is None:
                raise ValueError("Unknown recommendation interaction")
