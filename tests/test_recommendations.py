from __future__ import annotations

from decimal import Decimal

import pytest

from flooring_catalog.agent.models import ConversationPreferences
from flooring_catalog.ranking.models import (
    RankedCandidate,
    RankingScore,
    ScoreComponent,
    ScoreComponentName,
)
from flooring_catalog.recommendations import (
    ClientDomainSettings,
    ProductUrlBuilder,
    RecommendationCardService,
)
from flooring_catalog.search.models import HybridCandidate, SearchProduct


def ranked_product(
    *,
    sku: str = "ABC 1/2",
    name: str | None = "Coastal Oak",
    price: Decimal | None = Decimal("4.75"),
    gallery_images: str | None = "catalog.example/gallery.jpg",
) -> RankedCandidate:
    product = SearchProduct(
        sku=sku,
        name=name,
        z_prod_type="lvt",
        swatch="catalog.example/swatch.jpg",
        price=price,
        brand="Catalog Brand",
        material="Vinyl",
        color="Light Oak",
        style="Modern",
        description="Catalog description",
        gallery_images=gallery_images,
        waterproof="Yes",
        metadata={
            "application": "Residential",
            "features": ["Scratch Resistant", "Easy Clean"],
            "wear_layer": "20 mil",
            "carton_sq_ft": "20.25",
            "price_unit": "SF",
            "unapproved_dynamic_field": "must not be displayed",
        },
        semantic_similarity=0.9,
    )
    candidate = HybridCandidate(
        product=product,
        structured_match=True,
        semantic_similarity=0.9,
        retrieval_score=0.9,
    )
    component = ScoreComponent(
        name=ScoreComponentName.RETRIEVAL,
        raw_score=0.9,
        weight=1,
        contribution=0.9,
        reasons=("Catalog retrieval match.",),
    )
    return RankedCandidate(
        candidate=candidate,
        score=RankingScore(total=0.9, components=(component,)),
    )


def test_product_url_uses_only_configured_domain_and_encoded_catalog_sku() -> None:
    builder = ProductUrlBuilder("https://exampleflooring.com/")
    assert builder.for_sku("ABC 1/2") == "https://exampleflooring.com/?s=ABC+1%2F2"


@pytest.mark.parametrize(
    "domain",
    (
        "exampleflooring.com",
        "javascript:alert(1)",
        "https://user:secret@example.com",
        "https://example.com?redirect=evil.example",
        "https://example.com#fragment",
        "https://example.com/store",
        "https://exa mple.com",
    ),
)
def test_product_url_rejects_unregistered_domain_shapes(domain: str) -> None:
    with pytest.raises(ValueError, match="origin"):
        ProductUrlBuilder(domain)


def test_card_service_can_use_a_registered_domain_per_request() -> None:
    service = RecommendationCardService()
    preferences = ConversationPreferences(product_types=("lvt",))
    first = service.build(
        [ranked_product(sku="SKU-1")],
        preferences,
        client_domain="https://first.example",
    )[0]
    second = service.build(
        [ranked_product(sku="SKU-1")],
        preferences,
        client_domain="https://second.example",
    )[0]
    assert first.product_url == "https://first.example/?s=SKU-1"
    assert second.product_url == "https://second.example/?s=SKU-1"


def test_client_domain_settings_are_loaded_from_server_environment() -> None:
    settings = ClientDomainSettings.from_env(
        {"CLIENT_DOMAIN": "https://registered.example"}
    )
    assert settings.client_domain == "https://registered.example"
    with pytest.raises(ValueError, match="CLIENT_DOMAIN"):
        ClientDomainSettings.from_env({})


def test_recommendation_card_contains_catalog_facts_and_factual_reasons() -> None:
    service = RecommendationCardService("https://registered.example")
    cards = service.build(
        [ranked_product()],
        ConversationPreferences(
            product_types=("lvt",),
            colors=("Light Oak",),
            rooms=("kitchen",),
            budget_max_per_sq_ft=Decimal("5"),
            waterproof_required=True,
            has_pets=True,
        ),
    )
    card = cards[0]
    assert card.name == "Coastal Oak"
    assert card.sku == "ABC 1/2"
    assert card.swatch == "catalog.example/swatch.jpg"
    assert card.image == "catalog.example/gallery.jpg"
    assert card.price == Decimal("4.75")
    assert card.price_unit == "SF"
    assert card.carton_sq_ft == Decimal("20.25")
    assert card.product_url == "https://registered.example/?s=ABC+1%2F2"
    assert card.attributes == {
        "Product type": "lvt",
        "Brand": "Catalog Brand",
        "Material": "Vinyl",
        "Color": "Light Oak",
        "Style": "Modern",
        "Waterproof": "Yes",
        "Application": "Residential",
        "Features": "Scratch Resistant, Easy Clean",
        "Wear layer": "20 mil",
    }
    assert any("requested color: Light Oak" in reason for reason in card.reasons)
    assert any("within your requested budget" in reason for reason in card.reasons)
    assert any("Scratch Resistant" in reason for reason in card.reasons)


def test_missing_optional_catalog_values_are_not_invented() -> None:
    service = RecommendationCardService("https://registered.example")
    card = service.build(
        [ranked_product(name=None, price=None, gallery_images=None)],
        ConversationPreferences(rooms=("office",)),
    )[0]
    assert card.name == card.sku
    assert card.price is None
    assert card.image == card.swatch
    assert all("price" not in reason.casefold() for reason in card.reasons)
