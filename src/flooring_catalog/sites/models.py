"""Strict registered-site configuration models."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from flooring_catalog.recommendations import normalize_http_origin

SiteCode = Annotated[
    str,
    Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$"),
]


class SiteConfig(BaseModel):
    """Server-owned settings for one allowed storefront."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    site_code: SiteCode
    domain: str
    allowed_origins: tuple[str, ...] = Field(min_length=1)
    position: Literal["bottom-left", "bottom-right"] = "bottom-right"
    chatbot_title: str = Field(default="Flooring Assistant", min_length=1, max_length=100)

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
