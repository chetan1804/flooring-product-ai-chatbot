"""Strict registered-site configuration models."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from flooring_catalog.recommendations import normalize_http_origin

SiteCode = Annotated[
    str,
    Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
]


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


class WidgetTheme(BaseModel):
    """Validated visual and copy customization for one site's widget."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    primary_color: str = Field(default="#176b45", pattern=r"^#[0-9A-Fa-f]{6}$")
    primary_text_color: str = Field(default="#ffffff", pattern=r"^#[0-9A-Fa-f]{6}$")
    background_color: str = Field(default="#ffffff", pattern=r"^#[0-9A-Fa-f]{6}$")
    body_text_color: str = Field(default="#17211b", pattern=r"^#[0-9A-Fa-f]{6}$")
    muted_background_color: str = Field(default="#f5f8f6", pattern=r"^#[0-9A-Fa-f]{6}$")
    launcher_text: str = Field(default="Chat with us", min_length=1, max_length=40)
    welcome_message: str = Field(
        default="Tell me about the room and the flooring look you prefer.",
        min_length=1,
        max_length=300,
    )
    logo_url: HttpUrl | None = None

    @field_validator("logo_url")
    @classmethod
    def reject_logo_credentials(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value is not None and (value.username or value.password):
            raise ValueError("logo_url must not contain credentials")
        return value

    @model_validator(mode="after")
    def require_accessible_contrast(self) -> WidgetTheme:
        if _contrast_ratio(self.primary_color, self.primary_text_color) < 4.5:
            raise ValueError("primary colors must have a contrast ratio of at least 4.5:1")
        if _contrast_ratio(self.background_color, self.body_text_color) < 4.5:
            raise ValueError("body colors must have a contrast ratio of at least 4.5:1")
        if _contrast_ratio(self.muted_background_color, self.body_text_color) < 4.5:
            raise ValueError("muted colors must have a contrast ratio of at least 4.5:1")
        return self


class FlooringCalculatorConfig(BaseModel):
    """Per-site controls for the material estimator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = True
    default_waste_percent: int = Field(default=10, ge=0, le=30)
    max_room_dimension_feet: float = Field(default=500, gt=0, le=10_000)
    show_price_estimate: bool = True


class SiteConfig(BaseModel):
    """Server-owned settings for one allowed storefront."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    site_code: SiteCode
    domain: str
    allowed_origins: tuple[str, ...] = Field(min_length=1)
    position: Literal["bottom-left", "bottom-right"] = "bottom-right"
    chatbot_title: str = Field(default="Flooring Assistant", min_length=1, max_length=100)
    theme: WidgetTheme = Field(default_factory=WidgetTheme)
    calculator: FlooringCalculatorConfig = Field(default_factory=FlooringCalculatorConfig)

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        return normalize_http_origin(value)

    @field_validator("allowed_origins")
    @classmethod
    def validate_allowed_origins(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(normalize_http_origin(value) for value in values))
        if not normalized:
            raise ValueError("allowed_origins must contain at least one origin")
        return normalized

    @model_validator(mode="after")
    def require_storefront_origin(self) -> SiteConfig:
        if self.domain not in self.allowed_origins:
            raise ValueError("site domain must be included in allowed_origins")
        return self


class SiteRegistryDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sites: tuple[SiteConfig, ...] = Field(min_length=1)
