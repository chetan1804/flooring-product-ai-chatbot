"""Step 1 flooring catalog analysis and validation."""

from flooring_catalog.validation import (
    EligibilityResult,
    has_active_status,
    has_valid_swatch,
    validate_product,
)

__all__ = [
    "EligibilityResult",
    "has_active_status",
    "has_valid_swatch",
    "validate_product",
]

