"""Validated settings for the Step 8 single-site API deployment."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

SITE_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
POSITIONS = frozenset({"bottom-left", "bottom-right"})


def _valid_origin(origin: str) -> bool:
    parsed = urlsplit(origin)
    return bool(
        parsed.scheme in {"http", "https"}
        and parsed.hostname
        and not parsed.username
        and not parsed.password
        and parsed.path == ""
        and not parsed.query
        and not parsed.fragment
    )


@dataclass(frozen=True, slots=True)
class ApiSettings:
    site_code: str = "default"
    chatbot_title: str = "Flooring Assistant"
    widget_position: str = "bottom-right"
    cors_allow_origins: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not SITE_CODE_PATTERN.fullmatch(self.site_code):
            raise ValueError("SITE_CODE must contain 1-64 letters, numbers, '_' or '-'")
        if not self.chatbot_title.strip() or len(self.chatbot_title) > 100:
            raise ValueError("CHATBOT_TITLE must contain between 1 and 100 characters")
        if self.widget_position not in POSITIONS:
            raise ValueError("WIDGET_POSITION must be bottom-left or bottom-right")
        invalid_origin = any(not _valid_origin(origin) for origin in self.cors_allow_origins)
        if invalid_origin:
            raise ValueError("CORS_ALLOW_ORIGINS entries must be HTTP(S) origins")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> ApiSettings:
        values = os.environ if environ is None else environ
        origins = tuple(
            origin.strip()
            for origin in values.get("CORS_ALLOW_ORIGINS", "").split(",")
            if origin.strip()
        )
        return cls(
            site_code=values.get("SITE_CODE", "default").strip(),
            chatbot_title=values.get("CHATBOT_TITLE", "Flooring Assistant").strip(),
            widget_position=values.get("WIDGET_POSITION", "bottom-right").strip(),
            cors_allow_origins=origins,
        )
