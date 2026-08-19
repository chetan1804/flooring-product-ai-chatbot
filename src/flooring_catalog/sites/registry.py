"""JSON-backed registry for resolving trusted site configuration."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from pydantic import ValidationError

from flooring_catalog.sites.models import SiteConfig, SiteRegistryDocument


@dataclass(frozen=True, slots=True)
class SiteRegistrySettings:
    config_path: Path

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> SiteRegistrySettings:
        values = os.environ if environ is None else environ
        raw_path = values.get("SITE_CONFIG_PATH", "").strip()
        if not raw_path:
            raise ValueError("SITE_CONFIG_PATH is required")
        return cls(config_path=Path(raw_path).expanduser())


class SiteRegistry:
    """Immutable site-code lookup used by API requests and product-link generation."""

    def __init__(self, sites: Iterable[SiteConfig]) -> None:
        indexed: dict[str, SiteConfig] = {}
        for site in sites:
            if site.site_code in indexed:
                raise ValueError(f"duplicate site_code: {site.site_code}")
            indexed[site.site_code] = site
        if not indexed:
            raise ValueError("at least one site configuration is required")
        self._sites = MappingProxyType(indexed)

    @classmethod
    def from_file(cls, path: str | Path) -> SiteRegistry:
        config_path = Path(path)
        try:
            with config_path.open(encoding="utf-8") as handle:
                raw = json.load(handle)
        except FileNotFoundError as error:
            raise ValueError(f"site configuration file not found: {config_path}") from error
        except json.JSONDecodeError as error:
            raise ValueError(f"site configuration is not valid JSON: {config_path}") from error
        try:
            document = SiteRegistryDocument.model_validate(raw)
        except ValidationError as error:
            raise ValueError(f"invalid site configuration: {error}") from error
        return cls(document.sites)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> SiteRegistry:
        settings = SiteRegistrySettings.from_env(environ)
        return cls.from_file(settings.config_path)

    def get(self, site_code: str) -> SiteConfig | None:
        return self._sites.get(site_code)

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                origin
                for site in self._sites.values()
                for origin in site.allowed_origins
            )
        )
