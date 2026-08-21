from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from flooring_catalog.agent.models import (
    AgentAction,
    AgentTurnResult,
    ConversationPreferences,
)
from flooring_catalog.analytics import AnalyticsEventType, InMemoryAnalyticsStore
from flooring_catalog.api import create_app
from flooring_catalog.ranking.models import RankingScore, ScoreComponent, ScoreComponentName
from flooring_catalog.recommendations import ProductUrlBuilder
from flooring_catalog.recommendations.models import RecommendationCard
from flooring_catalog.sites import SiteConfig, SiteRegistry


def site_registry() -> SiteRegistry:
    return SiteRegistry(
        (
            SiteConfig(
                site_code="CLIENT001",
                domain="https://first.example",
                allowed_origins=("https://first.example",),
                chatbot_title="First Flooring Guide",
                position="bottom-right",
            ),
            SiteConfig(
                site_code="CLIENT002",
                domain="https://second.example",
                allowed_origins=("https://second.example", "https://www.second.example"),
                chatbot_title="Second Flooring Guide",
                position="bottom-left",
            ),
        )
    )


def recommendation(client_domain: str) -> RecommendationCard:
    score = RankingScore(
        total=0.9,
        components=(
            ScoreComponent(
                name=ScoreComponentName.RETRIEVAL,
                raw_score=0.9,
                weight=1,
                contribution=0.9,
                reasons=("Catalog retrieval match.",),
            ),
        ),
    )
    return RecommendationCard(
        sku="ABC123",
        name="Coastal Oak",
        swatch="catalog.example/swatch.jpg",
        image="catalog.example/room.jpg",
        price=Decimal("4.75"),
        attributes={"Product type": "lvt", "Waterproof": "Yes"},
        reasons=("Matches your requested product type: lvt.",),
        product_url=ProductUrlBuilder(client_domain).for_sku("ABC123"),
        ranking=score,
    )


class FakeAgent:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, str, str | None]] = []

    def respond(
        self,
        *,
        thread_id: str,
        user_message: str,
        client_domain: str | None = None,
    ) -> AgentTurnResult:
        self.calls.append((thread_id, user_message, client_domain))
        if self.error:
            raise self.error
        assert client_domain is not None
        return AgentTurnResult(
            action=AgentAction.CANDIDATES,
            message="I ranked 1 matching product.",
            preferences=ConversationPreferences(),
            candidate_skus=("ABC123",),
            recommendations=(recommendation(client_domain),),
        )


def test_health_site_configs_and_widget_are_served_without_database_access() -> None:
    app = create_app(agent=FakeAgent(), sites=site_registry())
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        first = client.get(
            "/api/config/CLIENT001", headers={"Origin": "https://first.example"}
        )
        second = client.get(
            "/api/config/CLIENT002", headers={"Origin": "https://second.example"}
        )
        first_config = first.json()
        assert {
            key: first_config[key]
            for key in ("site_code", "chatbot_title", "position")
        } == {
            "site_code": "CLIENT001",
            "chatbot_title": "First Flooring Guide",
            "position": "bottom-right",
        }
        assert first_config["theme"]["primary_color"] == "#176b45"
        assert first_config["theme"]["launcher_text"] == "Chat with us"
        assert first_config["calculator"]["default_waste_percent"] == 10
        assert second.json()["position"] == "bottom-left"
        assert client.get("/api/config/UNKNOWN").status_code == 404

        widget = client.get("/widget.js")
        assert widget.status_code == 200
        assert widget.headers["content-type"].startswith("application/javascript")
        assert "attachShadow" in widget.text
        assert "script.dataset.position" in widget.text
        assert "script.dataset.target" in widget.text
        assert "response.recommendations" in widget.text
        assert "textContent" in widget.text
        assert 'aria-label", "Close chat' in widget.text
        assert 'trackEvent("widget_opened"' in widget.text
        assert 'request("/api/feedback"' in widget.text
        assert "Estimated material cost" in widget.text
        assert "--fc-primary" in widget.text


def test_sessions_generate_links_from_each_registered_site_domain() -> None:
    agent = FakeAgent()
    app = create_app(agent=agent, sites=site_registry())
    with TestClient(app) as client:
        first_session = client.post(
            "/api/session",
            json={"site_code": "CLIENT001"},
            headers={"Origin": "https://first.example"},
        ).json()
        second_session = client.post(
            "/api/session",
            json={"site_code": "CLIENT002"},
            headers={"Origin": "https://www.second.example"},
        ).json()

        first = client.post(
            "/api/chat",
            json={"session_id": first_session["session_id"], "message": "Kitchen"},
            headers={"Origin": "https://first.example"},
        )
        second = client.post(
            "/api/chat",
            json={"session_id": second_session["session_id"], "message": "Kitchen"},
            headers={"Origin": "https://second.example"},
        )

    assert first.status_code == second.status_code == 200
    assert first.json()["recommendations"][0]["product_url"] == (
        "https://first.example/?s=ABC123"
    )
    assert second.json()["recommendations"][0]["product_url"] == (
        "https://second.example/?s=ABC123"
    )
    assert agent.calls[0][2] == "https://first.example"
    assert agent.calls[1][2] == "https://second.example"


def test_unknown_sites_sessions_and_cross_site_origins_are_rejected() -> None:
    app = create_app(agent=FakeAgent(), sites=site_registry())
    with TestClient(app) as client:
        assert client.post("/api/session", json={"site_code": "UNKNOWN"}).status_code == 404
        forbidden_session = client.post(
            "/api/session",
            json={"site_code": "CLIENT001"},
            headers={"Origin": "https://second.example"},
        )
        assert forbidden_session.status_code == 403

        session = client.post(
            "/api/session",
            json={"site_code": "CLIENT001"},
            headers={"Origin": "https://first.example"},
        ).json()
        forbidden_chat = client.post(
            "/api/chat",
            json={"session_id": session["session_id"], "message": "hello"},
            headers={"Origin": "https://second.example"},
        )
        assert forbidden_chat.status_code == 403
        assert (
            client.post(
                "/api/chat",
                json={
                    "session_id": "85d60cba-e03a-4f34-b285-ff4841e004f7",
                    "message": "hello",
                },
            ).status_code
            == 404
        )
        assert client.post("/api/chat", json={"message": "hello"}).status_code == 422


def test_chat_errors_are_sanitized() -> None:
    app = create_app(
        agent=FakeAgent(error=RuntimeError("secret database failure")),
        sites=site_registry(),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        session = client.post(
            "/api/session", json={"site_code": "CLIENT001"}
        ).json()
        response = client.post(
            "/api/chat",
            json={"session_id": session["session_id"], "message": "hello"},
        )
    assert response.status_code == 503
    assert response.json()["detail"] == "The recommendation service is temporarily unavailable"
    assert "secret" not in response.text


def test_cors_uses_the_union_of_registered_storefront_origins() -> None:
    app = create_app(agent=FakeAgent(), sites=site_registry())
    with TestClient(app) as client:
        allowed = client.options(
            "/api/session",
            headers={
                "Origin": "https://www.second.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        denied = client.options(
            "/api/session",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://www.second.example"
    assert "access-control-allow-origin" not in denied.headers


def test_analytics_feedback_and_product_clicks_are_session_bound() -> None:
    analytics = InMemoryAnalyticsStore()
    app = create_app(agent=FakeAgent(), sites=site_registry(), analytics=analytics)
    with TestClient(app) as client:
        session = client.post("/api/session", json={"site_code": "CLIENT001"}).json()
        assert (
            client.post(
                "/api/events",
                json={"session_id": session["session_id"], "event_type": "widget_opened"},
            ).status_code
            == 202
        )
        chat = client.post(
            "/api/chat",
            json={"session_id": session["session_id"], "message": "Kitchen"},
        ).json()
        assert (
            client.post(
                "/api/events",
                json={
                    "session_id": session["session_id"],
                    "event_type": "product_clicked",
                    "interaction_id": chat["interaction_id"],
                    "sku": "ABC123",
                },
            ).status_code
            == 202
        )
        first_feedback = client.post(
            "/api/feedback",
            json={
                "session_id": session["session_id"],
                "interaction_id": chat["interaction_id"],
                "rating": "helpful",
            },
        )
        replacement_feedback = client.post(
            "/api/feedback",
            json={
                "session_id": session["session_id"],
                "interaction_id": chat["interaction_id"],
                "rating": "not_helpful",
                "reason": "irrelevant",
            },
        )

    assert first_feedback.status_code == replacement_feedback.status_code == 201
    assert [event.event_type for event in analytics.events] == [
        AnalyticsEventType.SESSION_CREATED,
        AnalyticsEventType.WIDGET_OPENED,
        AnalyticsEventType.CHAT_COMPLETED,
        AnalyticsEventType.PRODUCT_CLICKED,
    ]
    assert analytics.events[2].recommendation_count == 1
    assert analytics.events[3].sku == "ABC123"
    assert len(analytics.feedback) == 1
    assert analytics.feedback[0].rating.value == "not_helpful"


def test_feedback_rejects_unknown_interactions_and_invalid_event_shapes() -> None:
    app = create_app(agent=FakeAgent(), sites=site_registry())
    with TestClient(app) as client:
        session = client.post("/api/session", json={"site_code": "CLIENT001"}).json()
        invalid_click = client.post(
            "/api/events",
            json={"session_id": session["session_id"], "event_type": "product_clicked"},
        )
        unknown_feedback = client.post(
            "/api/feedback",
            json={
                "session_id": session["session_id"],
                "interaction_id": "d24d7537-d249-4b00-9690-1c11676a4052",
                "rating": "helpful",
            },
        )
    assert invalid_click.status_code == 422
    assert unknown_feedback.status_code == 404
