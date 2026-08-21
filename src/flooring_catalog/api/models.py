"""Strict HTTP request and response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from flooring_catalog.agent.models import AgentAction
from flooring_catalog.analytics import AnalyticsEventType, FeedbackRating, FeedbackReason
from flooring_catalog.recommendations.models import RecommendationCard
from flooring_catalog.sites.models import FlooringCalculatorConfig, WidgetTheme


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
    interaction_id: UUID
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
    theme: WidgetTheme
    calculator: FlooringCalculatorConfig


class ClientAnalyticsEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: UUID
    event_type: Literal[AnalyticsEventType.WIDGET_OPENED, AnalyticsEventType.PRODUCT_CLICKED]
    interaction_id: UUID | None = None
    sku: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def validate_event_fields(self) -> ClientAnalyticsEventRequest:
        if self.event_type is AnalyticsEventType.PRODUCT_CLICKED:
            if self.interaction_id is None or self.sku is None:
                raise ValueError("product_clicked requires interaction_id and sku")
        elif self.interaction_id is not None or self.sku is not None:
            raise ValueError("widget_opened does not accept interaction_id or sku")
        return self


class RecommendationFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: UUID
    interaction_id: UUID
    rating: FeedbackRating
    reason: FeedbackReason | None = None


class AcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["accepted"] = "accepted"
