"""Single-pass profiling of a flooring product catalog."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from flooring_catalog.streaming import iter_json_array
from flooring_catalog.validation import is_empty_value, normalize_status, validate_product

MISSING = "<missing>"
BLANK = "<blank>"
NULL = "<null>"
REDACTED = "<redacted>"
SENSITIVE_PARTS = ("password", "secret", "token", "api_key", "email")


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _label(value: Any) -> str:
    if value is None:
        return NULL
    if isinstance(value, str):
        return value.strip() or BLANK
    if isinstance(value, (dict, list, tuple, set)) and not value:
        return BLANK
    return str(value)


def _sanitize(key: str, value: Any) -> Any:
    if any(part in key.casefold() for part in SENSITIVE_PARTS):
        return REDACTED
    if isinstance(value, str):
        return value if len(value) <= 120 else f"{value[:117]}..."
    if isinstance(value, list):
        return [_sanitize(key, item) for item in value[:3]]
    if isinstance(value, dict):
        return {nested_key: _sanitize(nested_key, nested) for nested_key, nested in value.items()}
    return value


def sanitize_product(product: dict[str, Any]) -> dict[str, Any]:
    """Preserve the real structure while truncating and redacting unsafe sample values."""

    return {key: _sanitize(key, value) for key, value in product.items()}


@dataclass(slots=True)
class FieldStats:
    present: int = 0
    null: int = 0
    blank: int = 0
    numeric_zero: int = 0
    types: Counter[str] = field(default_factory=Counter)

    def observe(self, value: Any) -> None:
        self.present += 1
        self.types[_type_name(value)] += 1
        if value is None:
            self.null += 1
        elif is_empty_value(value):
            self.blank += 1
        elif not isinstance(value, bool) and isinstance(value, (int, float)) and value == 0:
            self.numeric_zero += 1

    def report(self, total: int) -> dict[str, Any]:
        absent = total - self.present
        return {
            "present": self.present,
            "missing_key": absent,
            "null": self.null,
            "blank": self.blank,
            "numeric_zero": self.numeric_zero,
            "total_missing_or_empty": absent + self.null + self.blank,
            "observed_types": dict(sorted(self.types.items())),
        }


@dataclass(slots=True)
class SkuStats:
    present: int = 0
    empty: int = 0
    values: Counter[str] = field(default_factory=Counter)

    def observe(self, value: Any) -> None:
        self.present += 1
        if is_empty_value(value):
            self.empty += 1
        else:
            self.values[str(value).strip()] += 1


def _choose_sku_key(candidates: dict[str, SkuStats], explicit: str | None) -> str | None:
    if explicit:
        return explicit
    priority = {"sku": 0, "product_sku": 1, "sku_display": 2, "sku_manufacturer": 3}
    if not candidates:
        return None
    return min(candidates, key=lambda key: (priority.get(key.casefold(), 10), key))


def _sku_report(stats: SkuStats | None, total: int, key: str | None) -> dict[str, Any]:
    if key is None or stats is None:
        return {"key": None, "present": 0, "missing_key": total, "empty": 0,
                "unique_non_empty": 0, "duplicate_records": 0,
                "duplicate_values": 0, "top_duplicates": []}
    duplicates = sorted(
        ((value, count) for value, count in stats.values.items() if count > 1),
        key=lambda item: (-item[1], item[0]),
    )
    return {
        "key": key,
        "present": stats.present,
        "missing_key": total - stats.present,
        "empty": stats.empty,
        "unique_non_empty": len(stats.values),
        "duplicate_records": sum(count - 1 for _, count in duplicates),
        "duplicate_values": len(duplicates),
        "top_duplicates": [{"value": value, "count": count} for value, count in duplicates[:20]],
    }


@dataclass(slots=True)
class CatalogProfile:
    source_file: str
    total_products: int
    discovered_fields: list[str]
    sanitized_sample: dict[str, Any] | None
    z_prod_type_distribution: dict[str, int]
    status_distribution: dict[str, int]
    active_products: int
    rejected_status_not_active: int
    products_with_valid_swatch: int
    rejected_swatch_empty_or_missing: int
    eligible_products: int
    field_statistics: dict[str, dict[str, Any]]
    sku_statistics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def profile_catalog(path: str | Path, *, sku_key: str | None = None) -> CatalogProfile:
    """Profile the complete catalog in one pass while retaining only aggregate state."""

    total = active = valid_swatch = eligible = 0
    product_types: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    fields: dict[str, FieldStats] = {}
    sku_candidates: dict[str, SkuStats] = {}
    sample = None

    for product in iter_json_array(path):
        total += 1
        sample = sample or sanitize_product(product)
        for key, value in product.items():
            fields.setdefault(key, FieldStats()).observe(value)
            if "sku" in key.casefold() or key == sku_key:
                sku_candidates.setdefault(key, SkuStats()).observe(value)

        product_types[_label(product.get("z_prod_type", MISSING))] += 1
        normalized = normalize_status(product.get("status"))
        statuses[normalized or _label(product.get("status", MISSING))] += 1
        result = validate_product(product)
        active += int(result.active_status)
        valid_swatch += int(result.valid_swatch)
        eligible += int(result.eligible)

    selected_sku = _choose_sku_key(sku_candidates, sku_key)
    return CatalogProfile(
        source_file=Path(path).name,
        total_products=total,
        discovered_fields=sorted(fields),
        sanitized_sample=sample,
        z_prod_type_distribution=dict(sorted(product_types.items())),
        status_distribution=dict(sorted(statuses.items())),
        active_products=active,
        rejected_status_not_active=total - active,
        products_with_valid_swatch=valid_swatch,
        rejected_swatch_empty_or_missing=total - valid_swatch,
        eligible_products=eligible,
        field_statistics={key: fields[key].report(total) for key in sorted(fields)},
        sku_statistics=_sku_report(sku_candidates.get(selected_sku), total, selected_sku),
    )
