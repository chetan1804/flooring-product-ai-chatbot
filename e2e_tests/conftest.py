from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal

import pytest
import uvicorn
from fastapi.responses import HTMLResponse

from flooring_catalog.agent.models import AgentAction, AgentTurnResult, ConversationPreferences
from flooring_catalog.api import create_app
from flooring_catalog.ranking.models import RankingScore, ScoreComponent, ScoreComponentName
from flooring_catalog.recommendations import ProductUrlBuilder
from flooring_catalog.recommendations.models import RecommendationCard
from flooring_catalog.sites import FlooringCalculatorConfig, SiteConfig, SiteRegistry, WidgetTheme


def _available_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


def _recommendation(client_domain: str) -> RecommendationCard:
    score = RankingScore(
        total=0.93,
        components=(
            ScoreComponent(
                name=ScoreComponentName.RETRIEVAL,
                raw_score=0.93,
                weight=1,
                contribution=0.93,
                reasons=("Catalog retrieval match.",),
            ),
        ),
    )
    return RecommendationCard(
        sku="ABC123",
        name="Coastal Oak",
        swatch="https://images.example/coastal-oak.jpg",
        price=Decimal("4.75"),
        price_unit="SF",
        carton_sq_ft=Decimal("20"),
        attributes={"Product type": "lvt", "Waterproof": "Yes"},
        reasons=("Matches your requested waterproof luxury vinyl flooring.",),
        product_url=ProductUrlBuilder(client_domain).for_sku("ABC123"),
        ranking=score,
    )


class BrowserTestAgent:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    def respond(
        self,
        *,
        thread_id: str,
        user_message: str,
        client_domain: str | None = None,
    ) -> AgentTurnResult:
        self.calls.append((thread_id, user_message, client_domain))
        if user_message == "trigger service error":
            raise RuntimeError("simulated provider failure")
        assert client_domain is not None
        return AgentTurnResult(
            action=AgentAction.CANDIDATES,
            message="I ranked 1 matching product.",
            preferences=ConversationPreferences(),
            candidate_skus=("ABC123",),
            recommendations=(_recommendation(client_domain),),
        )


@dataclass(frozen=True, slots=True)
class BrowserTestServer:
    base_url: str
    agent: BrowserTestAgent


def _preview_html(*, inline: bool = False) -> str:
    target = '<div id="flooring-chatbot"></div>' if inline else ""
    target_attribute = ' data-target="#flooring-chatbot"' if inline else ""
    return f"""<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
  <body>
    <main><h1>Flooring Store Preview</h1>{target}</main>
    <script src="/widget.js" data-site="E2E"{target_attribute}></script>
  </body>
</html>"""


@pytest.fixture(scope="session")
def browser_test_server() -> Iterator[BrowserTestServer]:
    port = _available_port()
    base_url = f"http://127.0.0.1:{port}"
    agent = BrowserTestAgent()
    sites = SiteRegistry(
        (
            SiteConfig(
                site_code="E2E",
                domain=base_url,
                allowed_origins=(base_url,),
                position="bottom-right",
                chatbot_title="E2E Flooring Guide",
                theme=WidgetTheme(
                    primary_color="#5b2c6f",
                    primary_text_color="#ffffff",
                    muted_background_color="#f8f4fa",
                    launcher_text="Find my floor",
                    welcome_message="Let's find your ideal floor.",
                ),
                calculator=FlooringCalculatorConfig(
                    default_waste_percent=10,
                    max_room_dimension_feet=100,
                ),
            ),
        )
    )
    app = create_app(agent=agent, sites=sites)

    @app.get("/preview", response_class=HTMLResponse, include_in_schema=False)
    def preview() -> str:
        return _preview_html()

    @app.get("/preview-inline", response_class=HTMLResponse, include_in_schema=False)
    def preview_inline() -> str:
        return _preview_html(inline=True)

    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("browser test server did not start")

    yield BrowserTestServer(base_url=base_url, agent=agent)

    server.should_exit = True
    thread.join(timeout=10)
