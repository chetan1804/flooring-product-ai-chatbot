"""Strict HTTP request and response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from flooring_catalog.agent.models import AgentAction
from flooring_catalog.recommendations.models import RecommendationCard


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    site_code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class SessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: UUID
    site_code: str
    created_at: datetime


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    session_id: UUID
    message: str = Field(min_length=1, max_length=4_000)


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: UUID
    action: AgentAction
    message: str
    recommendations: tuple[RecommendationCard, ...] = ()


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok", "unavailable"] = "ok"


class WidgetConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    site_code: str
    chatbot_title: str
    position: str
