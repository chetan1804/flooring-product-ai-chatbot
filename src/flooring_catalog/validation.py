"""Reusable validation rules for product ingestion eligibility."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any


def normalize_status(value: Any) -> str | None:
    """Normalize a textual product status safely."""

    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    return normalized or None


def has_active_status(product: Mapping[str, Any]) -> bool:
    """Accept active status regardless of reasonable case or surrounding whitespace."""

    return normalize_status(product.get("status")) == "active"


def is_empty_value(value: Any) -> bool:
    """Detect empty values without treating numeric zero or false as missing."""

    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, Collection) and not isinstance(value, (str, bytes, bytearray)):
        return len(value) == 0
    return False


def has_valid_swatch(product: Mapping[str, Any]) -> bool:
    """Require a present, non-null, non-empty swatch value."""

    return "swatch" in product and not is_empty_value(product["swatch"])


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    """The independently testable outcomes of all Step 1 eligibility rules."""

    active_status: bool
    valid_swatch: bool

    @property
    def eligible(self) -> bool:
        return self.active_status and self.valid_swatch


def validate_product(product: Mapping[str, Any]) -> EligibilityResult:
    """Evaluate all current eligibility rules for one catalog product."""

    return EligibilityResult(
        active_status=has_active_status(product),
        valid_swatch=has_valid_swatch(product),
    )

