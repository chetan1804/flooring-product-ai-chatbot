from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from flooring_catalog.agent.models import (
    AgentAction,
    AgentTurnResult,
    ConversationPreferences,
)
from flooring_catalog.api import create_app
from flooring_catalog.api.settings import ApiSettings
from flooring_catalog.ranking.models import RankingScore, ScoreComponent, ScoreComponentName
from flooring_catalog.recommendations.models import RecommendationCard


def recommendation() -> RecommendationCard:
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
        product_url="https://shop.example/?s=ABC123",
        ranking=score,
    )


class FakeAgent:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def respond(self, *, thread_id: str, user_message: str) -> AgentTurnResult:
        self.calls.append((thread_id, user_message))
        if self.error:
            raise self.error
        return AgentTurnResult(
            action=AgentAction.CANDIDATES,
            message="I ranked 1 matching product.",
            preferences=ConversationPreferences(),
            candidate_skus=("ABC123",),
            recommendations=(recommendation(),),
        )


def settings(**values: Any) -> ApiSettings:
    defaults: dict[str, Any] = {
        "site_code": "CLIENT001",
        "chatbot_title": "Flooring Guide",
        "widget_position": "bottom-right",
        "cors_allow_origins": ("https://shop.example",),
    }
    defaults.update(values)
    return ApiSettings(**defaults)


def test_health_config_and_widget_are_served_without_database_access() -> None:
    app = create_app(agent=FakeAgent(), settings=settings())
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        config = client.get("/api/config/CLIENT001")
        assert config.status_code == 200
        assert config.json() == {
            "site_code": "CLIENT001",
            "chatbot_title": "Flooring Guide",
            "position": "bottom-right",
        }
        assert client.get("/api/config/UNKNOWN").status_code == 404

        widget = client.get("/widget.js")
        assert widget.status_code == 200
        assert widget.headers["content-type"].startswith("application/javascript")
        assert "attachShadow" in widget.text
        assert "response.recommendations" in widget.text
        assert "textContent" in widget.text


def test_session_and_chat_return_validated_recommendation_dto() -> None:
    agent = FakeAgent()
    app = create_app(agent=agent, settings=settings())
    with TestClient(app) as client:
        session_response = client.post("/api/session", json={"site_code": "CLIENT001"})
        assert session_response.status_code == 201
        session = session_response.json()

        response = client.post(
            "/api/chat",
            json={"session_id": session["session_id"], "message": "Light oak for kitchen"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["session_id"] == session["session_id"]
        assert body["action"] == "candidates"
        assert body["recommendations"][0]["sku"] == "ABC123"
        assert body["recommendations"][0]["price"] == "4.75"
        assert body["recommendations"][0]["product_url"] == (
            "https://shop.example/?s=ABC123"
        )
        assert agent.calls == [(session["session_id"], "Light oak for kitchen")]


def test_unknown_site_session_and_invalid_payloads_are_rejected() -> None:
    app = create_app(agent=FakeAgent(), settings=settings())
    with TestClient(app) as client:
        assert client.post("/api/session", json={"site_code": "UNKNOWN"}).status_code == 404
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
        session = client.post("/api/session", json={"site_code": "CLIENT001"}).json()
        assert (
            client.post(
                "/api/chat",
                json={"session_id": session["session_id"], "message": "   "},
            ).status_code
            == 422
        )


def test_chat_errors_are_sanitized() -> None:
    app = create_app(
        agent=FakeAgent(error=RuntimeError("secret database failure")),
        settings=settings(),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        session = client.post("/api/session", json={"site_code": "CLIENT001"}).json()
        response = client.post(
            "/api/chat",
            json={"session_id": session["session_id"], "message": "hello"},
        )
    assert response.status_code == 503
    assert response.json()["detail"] == "The recommendation service is temporarily unavailable"
    assert "secret" not in response.text


def test_cors_allows_only_configured_storefront_origin() -> None:
    app = create_app(agent=FakeAgent(), settings=settings())
    with TestClient(app) as client:
        allowed = client.options(
            "/api/session",
            headers={
                "Origin": "https://shop.example",
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
    assert allowed.headers["access-control-allow-origin"] == "https://shop.example"
    assert "access-control-allow-origin" not in denied.headers


@pytest.mark.parametrize(
    "values",
    (
        {"site_code": "bad code"},
        {"widget_position": "top-right"},
        {"cors_allow_origins": ("javascript:alert(1)",)},
        {"cors_allow_origins": ("https://shop.example/path",)},
        {"cors_allow_origins": ("https://user:secret@shop.example",)},
    ),
)
def test_api_settings_reject_unsafe_values(values: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        settings(**values)
