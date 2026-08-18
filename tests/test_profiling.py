from __future__ import annotations

import json

from flooring_catalog.profiling import REDACTED, profile_catalog


def test_profile_counts_rules_missing_values_and_duplicate_skus(tmp_path) -> None:
    products = [
        {"sku": "A1", "status": " ACTIVE ", "swatch": "a.jpg",
         "z_prod_type": "carpet", "price": 0, "api_token": "hidden"},
        {"sku": "A1", "status": "inactive", "swatch": "b.jpg",
         "z_prod_type": "carpet", "price": None},
        {"sku": "B2", "status": "active", "swatch": " ", "z_prod_type": "tile"},
        {"status": "active", "swatch": ["c.jpg"]},
    ]
    path = tmp_path / "products.json"
    path.write_text(json.dumps(products), encoding="utf-8")
    profile = profile_catalog(path)

    assert profile.total_products == 4
    assert profile.z_prod_type_distribution == {"<missing>": 1, "carpet": 2, "tile": 1}
    assert profile.status_distribution == {"active": 3, "inactive": 1}
    assert profile.active_products == 3
    assert profile.products_with_valid_swatch == 3
    assert profile.eligible_products == 2
    assert profile.field_statistics["price"]["missing_key"] == 2
    assert profile.field_statistics["price"]["null"] == 1
    assert profile.field_statistics["price"]["numeric_zero"] == 1
    assert profile.sanitized_sample["api_token"] == REDACTED
    assert profile.sku_statistics["duplicate_records"] == 1
    assert profile.sku_statistics["duplicate_values"] == 1
    assert profile.sku_statistics["key"] == "sku"


def test_explicit_nonstandard_sku_key(tmp_path) -> None:
    path = tmp_path / "products.json"
    path.write_text('[{"item_number": "X"}]', encoding="utf-8")
    assert profile_catalog(path, sku_key="item_number").sku_statistics["key"] == "item_number"

