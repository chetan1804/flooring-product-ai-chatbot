from __future__ import annotations

import pytest

from flooring_catalog.validation import (
    has_active_status,
    has_valid_swatch,
    is_empty_value,
    validate_product,
)


def test_active_product_is_accepted() -> None:
    assert validate_product({"status": "active", "swatch": "image.jpg"}).eligible


def test_inactive_product_is_rejected() -> None:
    assert not has_active_status({"status": "inactive"})


@pytest.mark.parametrize("status", ["ACTIVE", " Active ", "\tAcTiVe\n"])
def test_status_normalizes_case_and_whitespace(status: str) -> None:
    assert has_active_status({"status": status})


@pytest.mark.parametrize("product", [{}, {"swatch": None}, {"swatch": ""},
                                      {"swatch": " \t"}, {"swatch": []}, {"swatch": {}}])
def test_missing_or_empty_swatch_is_rejected(product: dict[str, object]) -> None:
    assert not has_valid_swatch(product)


@pytest.mark.parametrize("swatch", ["image.jpg", ["image.jpg"], {"url": "image.jpg"}])
def test_valid_swatch_is_accepted(swatch: object) -> None:
    assert has_valid_swatch({"swatch": swatch})


def test_z_prod_type_is_preserved() -> None:
    product = {"status": "active", "swatch": "x", "z_prod_type": "Luxury Vinyl"}
    validate_product(product)
    assert product["z_prod_type"] == "Luxury Vinyl"


def test_zero_is_not_missing() -> None:
    assert not is_empty_value(0)
    assert not is_empty_value(0.0)

