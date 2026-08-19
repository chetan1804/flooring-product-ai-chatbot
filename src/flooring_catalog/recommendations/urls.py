"""Server-owned client-domain configuration and safe SKU URL generation."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit, urlunsplit


@dataclass(frozen=True, slots=True)
class ClientDomainSettings:
    """Single registered client domain; Step 9 will add multi-site lookup."""

    client_domain: str

    def __post_init__(self) -> None:
        # Validate eagerly so an unsafe deployment setting fails at startup.
        ProductUrlBuilder(self.client_domain)

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> ClientDomainSettings:
        values = os.environ if environ is None else environ
        domain = values.get("CLIENT_DOMAIN", "").strip()
        if not domain:
            raise ValueError("CLIENT_DOMAIN is required")
        return cls(client_domain=domain)


class ProductUrlBuilder:
    """Build links from a pre-registered domain and a catalog SKU only."""

    def __init__(self, client_domain: str) -> None:
        normalized = client_domain.strip()
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("client domain must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password:
            raise ValueError("client domain cannot contain credentials")
        if parsed.query or parsed.fragment:
            raise ValueError("client domain cannot contain a query or fragment")
        if parsed.path not in {"", "/"}:
            raise ValueError("client domain must not contain a path")
        if any(character.isspace() for character in parsed.netloc):
            raise ValueError("client domain cannot contain whitespace")
        try:
            port = parsed.port
        except ValueError as error:
            raise ValueError("client domain contains an invalid port") from error
        if port == 0:
            raise ValueError("client domain contains an invalid port")
        self._base_url = urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))

    def for_sku(self, sku: str) -> str:
        normalized_sku = sku.strip()
        if not normalized_sku:
            raise ValueError("SKU is required to generate a product URL")
        return f"{self._base_url}?{urlencode({'s': normalized_sku})}"
