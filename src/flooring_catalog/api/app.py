"""FastAPI application factory with testable dependency injection."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from flooring_catalog.agent.models import AgentTurnResult
from flooring_catalog.api.models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    SessionCreateRequest,
    SessionResponse,
    WidgetConfigResponse,
)
from flooring_catalog.api.runtime import RuntimeResources, build_runtime_resources
from flooring_catalog.api.sessions import InMemorySessionStore
from flooring_catalog.api.settings import ApiSettings

LOGGER = logging.getLogger(__name__)
WIDGET_PATH = Path(__file__).parent.parent / "static" / "widget.js"


class ConversationAgent(Protocol):
    def respond(self, *, thread_id: str, user_message: str) -> AgentTurnResult:
        """Run one validated conversation turn."""


def create_app(
    *,
    agent: ConversationAgent | None = None,
    settings: ApiSettings | None = None,
    sessions: InMemorySessionStore | None = None,
) -> FastAPI:
    """Create an API; production resources are lazy and tests can inject fakes."""

    api_settings = settings or ApiSettings.from_env()
    session_store = sessions or InMemorySessionStore()
    runtime: RuntimeResources | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal runtime
        if agent is not None:
            app.state.agent = agent
        else:
            runtime = build_runtime_resources()
            app.state.agent = runtime.agent
        yield
        if runtime is not None:
            runtime.close()

    app = FastAPI(
        title="Flooring Product Recommendation API",
        version="0.1.0",
        lifespan=lifespan,
    )
    if api_settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(api_settings.cors_allow_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/api/config/{site_code}", response_model=WidgetConfigResponse)
    def widget_config(site_code: str) -> WidgetConfigResponse:
        if site_code != api_settings.site_code:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown site")
        return WidgetConfigResponse(
            site_code=api_settings.site_code,
            chatbot_title=api_settings.chatbot_title,
            position=api_settings.widget_position,
        )

    @app.post(
        "/api/session",
        response_model=SessionResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_session(payload: SessionCreateRequest) -> SessionResponse:
        if payload.site_code != api_settings.site_code:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown site")
        record = session_store.create(payload.site_code)
        return SessionResponse(
            session_id=record.session_id,
            site_code=record.site_code,
            created_at=record.created_at,
        )

    @app.post("/api/chat", response_model=ChatResponse)
    def chat(payload: ChatRequest, request: Request) -> ChatResponse:
        record = session_store.get(payload.session_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown session")
        try:
            result = request.app.state.agent.respond(
                thread_id=str(record.session_id),
                user_message=payload.message,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(error),
            ) from error
        except Exception as error:
            LOGGER.exception(
                "Chat processing failed for site=%s session=%s",
                record.site_code,
                record.session_id,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The recommendation service is temporarily unavailable",
            ) from error
        return ChatResponse(
            session_id=record.session_id,
            action=result.action,
            message=result.message,
            recommendations=result.recommendations,
        )

    @app.get("/widget.js", include_in_schema=False)
    def widget_script() -> FileResponse:
        return FileResponse(
            WIDGET_PATH,
            media_type="application/javascript",
            headers={"Cache-Control": "public, max-age=300"},
        )

    return app
