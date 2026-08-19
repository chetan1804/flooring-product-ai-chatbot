from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from flooring_catalog.sites import SiteConfig, SiteRegistry, SiteRegistrySettings


def site(site_code: str = "CLIENT001", domain: str = "https://shop.example") -> SiteConfig:
    return SiteConfig(
        site_code=site_code,
        domain=domain,
        allowed_origins=(domain,),
    )


def test_site_config_normalizes_origins_and_validates_storefront() -> None:
    config = SiteConfig(
        site_code="CLIENT001",
        domain="https://shop.example/",
        allowed_origins=("https://shop.example/", "https://www.shop.example"),
        position="bottom-left",
    )
    assert config.domain == "https://shop.example"
    assert config.allowed_origins == (
        "https://shop.example",
        "https://www.shop.example",
    )
    with pytest.raises(ValidationError, match="included"):
        SiteConfig(
            site_code="CLIENT001",
            domain="https://shop.example",
            allowed_origins=("https://other.example",),
        )


@pytest.mark.parametrize(
    "values",
    (
        {"site_code": "bad code"},
        {"domain": "javascript:alert(1)"},
        {"domain": "https://user:secret@shop.example"},
        {"allowed_origins": ("https://shop.example/path",)},
        {"position": "top-right"},
    ),
)
def test_site_config_rejects_unsafe_values(values: dict[str, object]) -> None:
    defaults: dict[str, object] = {
        "site_code": "CLIENT001",
        "domain": "https://shop.example",
        "allowed_origins": ("https://shop.example",),
    }
    defaults.update(values)
    with pytest.raises(ValidationError):
        SiteConfig.model_validate(defaults)


def test_registry_rejects_duplicates_and_collects_origins() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        SiteRegistry((site(), site()))
    registry = SiteRegistry(
        (
            site(),
            SiteConfig(
                site_code="CLIENT002",
                domain="https://second.example",
                allowed_origins=("https://second.example", "https://shop.example"),
            ),
        )
    )
    assert registry.get("CLIENT002") is not None
    assert registry.get("UNKNOWN") is None
    assert registry.allowed_origins == (
        "https://shop.example",
        "https://second.example",
    )


def test_registry_loads_validated_json_from_environment(tmp_path: Path) -> None:
    path = tmp_path / "sites.json"
    path.write_text(
        json.dumps(
            {
                "sites": [
                    {
                        "site_code": "CLIENT001",
                        "domain": "https://shop.example",
                        "allowed_origins": ["https://shop.example"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    registry = SiteRegistry.from_env({"SITE_CONFIG_PATH": str(path)})
    assert registry.get("CLIENT001") == site()
    assert SiteRegistrySettings.from_env(
        {"SITE_CONFIG_PATH": str(path)}
    ).config_path == path


def test_registry_reports_missing_and_invalid_files(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="SITE_CONFIG_PATH"):
        SiteRegistry.from_env({})
    with pytest.raises(ValueError, match="not found"):
        SiteRegistry.from_file(tmp_path / "missing.json")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        SiteRegistry.from_file(invalid)
