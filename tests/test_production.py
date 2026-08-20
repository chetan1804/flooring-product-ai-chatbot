from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from flooring_catalog.agent.models import AgentAction, AgentTurnResult, ConversationPreferences
from flooring_catalog.api import create_app
from flooring_catalog.api.sessions import InMemorySessionStore
from flooring_catalog.production import AppEnvironment, ProductionSettings
from flooring_catalog.production.logging import JsonLogFormatter
from flooring_catalog.sites import SiteConfig, SiteRegistry


class FakeAgent:
    def respond(
        self,
        *,
        thread_id: str,
        user_message: str,
        client_domain: str | None = None,
    ) -> AgentTurnResult:
        return AgentTurnResult(
            action=AgentAction.NO_RESULTS,
            message="No matching products.",
            preferences=ConversationPreferences(),
        )


def site_registry() -> SiteRegistry:
    return SiteRegistry(
        (
            SiteConfig(
                site_code="CLIENT001",
                domain="https://shop.example",
                allowed_origins=("https://shop.example",),
            ),
        )
    )


def production_settings(**values: object) -> ProductionSettings:
    defaults: dict[str, object] = {
        "environment": AppEnvironment.PRODUCTION,
        "allowed_hosts": ("testserver",),
        "docs_enabled": False,
    }
    defaults.update(values)
    return ProductionSettings(**defaults)


def test_production_settings_load_bounded_operational_values() -> None:
    settings = ProductionSettings.from_env(
        {
            "APP_ENV": "production",
            "LANGGRAPH_STRICT_MSGPACK": "true",
            "ALLOWED_HOSTS": "api.example.com,internal.example.com",
            "LOG_LEVEL": "WARNING",
            "DATABASE_POOL_MIN_SIZE": "2",
            "DATABASE_POOL_MAX_SIZE": "12",
            "OPENAI_TIMEOUT_SECONDS": "20",
            "OPENAI_MAX_RETRIES": "3",
        }
    )
    assert settings.environment is AppEnvironment.PRODUCTION
    assert settings.allowed_hosts == ("api.example.com", "internal.example.com")
    assert settings.docs_enabled is False
    assert settings.database_pool_min_size == 2
    assert settings.database_pool_max_size == 12
    assert settings.openai_timeout_seconds == 20
    assert settings.openai_max_retries == 3


@pytest.mark.parametrize(
    ("environment", "message"),
    (
        ({"APP_ENV": "production"}, "LANGGRAPH_STRICT_MSGPACK"),
        (
            {
                "APP_ENV": "production",
                "LANGGRAPH_STRICT_MSGPACK": "true",
                "ALLOWED_HOSTS": "*",
            },
            "ALLOWED_HOSTS",
        ),
        ({"DATABASE_POOL_MIN_SIZE": "20", "DATABASE_POOL_MAX_SIZE": "10"}, "cannot exceed"),
        ({"MAX_REQUEST_BODY_BYTES": "0"}, "must be positive"),
        ({"OPENAI_MAX_RETRIES": "11"}, "between 0 and 10"),
    ),
)
def test_invalid_production_settings_fail_fast(
    environment: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        ProductionSettings.from_env(environment)


def test_json_logs_are_structured_without_exception_text() -> None:
    formatter = JsonLogFormatter()
    try:
        raise RuntimeError("sensitive failure detail")
    except RuntimeError:
        record = logging.getLogger("test").makeRecord(
            "test",
            logging.ERROR,
            __file__,
            1,
            "operation failed",
            (),
            exc_info=sys.exc_info(),
            extra={"event": "test_event", "request_id": "request-1"},
        )
    payload = json.loads(formatter.format(record))
    assert payload["message"] == "operation failed"
    assert payload["event"] == "test_event"
    assert payload["request_id"] == "request-1"
    assert payload["error_type"] == "RuntimeError"
    assert "sensitive failure detail" not in json.dumps(payload)


def test_http_hardening_readiness_and_docs_configuration() -> None:
    app = create_app(
        agent=FakeAgent(),
        sites=site_registry(),
        production=production_settings(max_request_body_bytes=80),
        readiness_check=lambda: True,
    )
    with TestClient(app) as client:
        health = client.get("/api/health", headers={"X-Request-ID": "known-request"})
        generated_id = client.get("/api/health", headers={"X-Request-ID": "invalid id!"})
        ready = client.get("/api/ready")
        too_large = client.post(
            "/api/session",
            content=b"x" * 81,
            headers={"Content-Type": "application/json"},
        )
        docs = client.get("/docs")
        untrusted_host = client.get("/api/health", headers={"Host": "evil.example"})
    assert health.status_code == 200
    assert health.headers["x-request-id"] == "known-request"
    assert health.headers["x-content-type-options"] == "nosniff"
    assert health.headers["referrer-policy"] == "no-referrer"
    assert "max-age" in health.headers["strict-transport-security"]
    assert generated_id.headers["x-request-id"] != "invalid id!"
    assert ready.status_code == 200
    assert too_large.status_code == 413
    assert too_large.json() == {"detail": "Request body too large"}
    assert docs.status_code == 404
    assert untrusted_host.status_code == 400


def test_failed_readiness_returns_service_unavailable() -> None:
    app = create_app(
        agent=FakeAgent(),
        sites=site_registry(),
        production=production_settings(),
        readiness_check=lambda: False,
    )
    with TestClient(app) as client:
        response = client.get("/api/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Service unavailable"}


def test_in_memory_sessions_expire_and_evict_oldest() -> None:
    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    store = InMemorySessionStore(
        ttl_seconds=10,
        max_sessions=1,
        clock=lambda: now[0],
    )
    first = store.create("CLIENT001")
    now[0] += timedelta(seconds=1)
    second = store.create("CLIENT002")
    assert store.get(first.session_id) is None
    assert store.get(second.session_id) is not None
    now[0] += timedelta(seconds=11)
    assert store.get(second.session_id) is None
