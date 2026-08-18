from __future__ import annotations

import json

import pytest

from flooring_catalog.streaming import CatalogFormatError, iter_json_array


def test_streams_across_small_chunks(tmp_path) -> None:
    products = [{"sku": "A", "name": "Café Oak"}, {"sku": "B", "colors": ["tan"]}]
    path = tmp_path / "products.json"
    path.write_text(json.dumps(products), encoding="utf-8")
    assert list(iter_json_array(path, chunk_size=7)) == products


def test_rejects_non_object_product(tmp_path) -> None:
    path = tmp_path / "products.json"
    path.write_text('[{"sku": "A"}, 4]', encoding="utf-8")
    with pytest.raises(CatalogFormatError, match="product 2 must be a JSON object"):
        list(iter_json_array(path, chunk_size=4))


def test_rejects_non_array_catalog(tmp_path) -> None:
    path = tmp_path / "products.json"
    path.write_text('{"sku": "A"}', encoding="utf-8")
    with pytest.raises(CatalogFormatError, match="top-level value must be a JSON array"):
        list(iter_json_array(path))

