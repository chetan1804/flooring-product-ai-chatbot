from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from flooring_catalog.sites import SiteConfig, SiteRegistry, SiteRegistrySettings, WidgetTheme


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
    assert config.theme.launcher_text == "Chat with us"
    assert config.calculator.default_waste_percent == 10
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


def test_widget_theme_validates_colors_contrast_copy_and_logo() -> None:
    theme = WidgetTheme(
        primary_color="#5b2c6f",
        primary_text_color="#ffffff",
        launcher_text="Find my floor",
        welcome_message="Welcome to the flooring guide.",
        logo_url="https://cdn.example/brand/logo.svg",
    )
    assert theme.launcher_text == "Find my floor"
    assert str(theme.logo_url) == "https://cdn.example/brand/logo.svg"

    with pytest.raises(ValidationError, match="contrast"):
        WidgetTheme(primary_color="#ffffff", primary_text_color="#eeeeee")
    with pytest.raises(ValidationError):
        WidgetTheme(primary_color="green")
    with pytest.raises(ValidationError, match="credentials"):
        WidgetTheme(logo_url="https://user:secret@cdn.example/logo.svg")


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
    inline = SiteRegistry.from_env({"SITE_CONFIG_JSON": path.read_text(encoding="utf-8")})
    assert inline.get("CLIENT001") == site()


def test_registry_reports_missing_and_invalid_files(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        SiteRegistry.from_env({})
    with pytest.raises(ValueError, match="exactly one"):
        SiteRegistry.from_env({"SITE_CONFIG_PATH": "x", "SITE_CONFIG_JSON": "{}"})
    with pytest.raises(ValueError, match="not found"):
        SiteRegistry.from_file(tmp_path / "missing.json")
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        SiteRegistry.from_file(invalid)
