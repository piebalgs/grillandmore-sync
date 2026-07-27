"""Testi universālajam GrillAndMore produkta modelim."""

import pytest

from src.gmps.models import Product, ProductFeature, ProductImage


def test_product_creation() -> None:
    """Produktu var izveidot ar obligātajiem laukiem."""

    product = Product(
        brand="Weber",
        sku="1500186",
    )

    assert product.brand == "Weber"
    assert product.sku == "1500186"
    assert product.status == "draft"
    assert product.gmps_score == 0
    assert product.gmps_level == "basic"


def test_product_text_fields_are_trimmed() -> None:
    """Galvenajiem teksta laukiem tiek noņemtas liekās atstarpes."""

    product = Product(
        brand="  Weber  ",
        sku="  1500186  ",
        name="  Spirit EP-425 gāzes grils  ",
        product_type="  Gas Grill  ",
    )

    assert product.brand == "Weber"
    assert product.sku == "1500186"
    assert product.name == "Spirit EP-425 gāzes grils"
    assert product.product_type == "gas grill"


def test_empty_brand_is_rejected() -> None:
    """Produktu nevar izveidot bez zīmola."""

    with pytest.raises(
        ValueError,
        match="Produkta zīmols nedrīkst būt tukšs",
    ):
        Product(
            brand="",
            sku="1500186",
        )


def test_empty_sku_is_rejected() -> None:
    """Produktu nevar izveidot bez SKU."""

    with pytest.raises(
        ValueError,
        match="Produkta SKU nedrīkst būt tukšs",
    ):
        Product(
            brand="Weber",
            sku="",
        )


@pytest.mark.parametrize("score", [-1, 101])
def test_invalid_gmps_score_is_rejected(score: int) -> None:
    """GMPS vērtējumam jābūt diapazonā no 0 līdz 100."""

    with pytest.raises(
        ValueError,
        match="GMPS vērtējumam jābūt diapazonā",
    ):
        Product(
            brand="Weber",
            sku="1500186",
            gmps_score=score,
        )


def test_valid_gmps_score_is_accepted() -> None:
    """Korekts GMPS vērtējums tiek saglabāts."""

    product = Product(
        brand="Weber",
        sku="1500186",
        gmps_score=85,
    )

    assert product.gmps_score == 85


def test_display_name_adds_brand() -> None:
    """Zīmols tiek pievienots nosaukumam, ja tā tur vēl nav."""

    product = Product(
        brand="Weber",
        sku="1500186",
        name="Spirit EP-425 gāzes grils",
    )

    assert product.display_name == "Weber Spirit EP-425 gāzes grils"


def test_display_name_does_not_duplicate_brand() -> None:
    """Zīmols nosaukumā netiek dublēts."""

    product = Product(
        brand="Weber",
        sku="1500186",
        name="Weber Spirit EP-425 gāzes grils",
    )

    assert product.display_name == "Weber Spirit EP-425 gāzes grils"


def test_display_name_falls_back_to_sku() -> None:
    """Ja nosaukuma nav, tiek izmantots zīmols un SKU."""

    product = Product(
        brand="Weber",
        sku="1500186",
    )

    assert product.display_name == "Weber 1500186"


def test_add_feature() -> None:
    """Produktam var pievienot funkciju."""

    product = Product(
        brand="Weber",
        sku="1500186",
    )

    product.add_feature(
        title="Četri degļi",
        description="Nodrošina vienmērīgu karstuma sadalījumu.",
    )

    assert len(product.features) == 1
    assert isinstance(product.features[0], ProductFeature)
    assert product.features[0].title == "Četri degļi"
    assert (
        product.features[0].description
        == "Nodrošina vienmērīgu karstuma sadalījumu."
    )


def test_empty_feature_is_not_added() -> None:
    """Funkcija bez virsraksta netiek pievienota."""

    product = Product(
        brand="Weber",
        sku="1500186",
    )

    product.add_feature(
        title="",
        description="Apraksts bez virsraksta.",
    )

    assert product.features == []


def test_add_image() -> None:
    """Produktam var pievienot derīgu attēla URL."""

    product = Product(
        brand="Weber",
        sku="1500186",
    )

    product.add_image(
        url="https://example.com/weber-spirit.jpg",
        alt_text="Weber Spirit EP-425 gāzes grils",
    )

    assert len(product.images) == 1
    assert isinstance(product.images[0], ProductImage)
    assert (
        product.images[0].url
        == "https://example.com/weber-spirit.jpg"
    )
    assert (
        product.images[0].alt_text
        == "Weber Spirit EP-425 gāzes grils"
    )


def test_invalid_image_url_is_not_added() -> None:
    """Iekšējs faila ceļš netiek pievienots kā publisks attēls."""

    product = Product(
        brand="Weber",
        sku="1500186",
    )

    product.add_image(
        url="VOLUMES:VDB:images:weber.jpg",
    )

    assert product.images == []


def test_duplicate_image_is_not_added() -> None:
    """Vienu un to pašu attēlu nevar pievienot divreiz."""

    product = Product(
        brand="Weber",
        sku="1500186",
    )

    image_url = "https://example.com/weber-spirit.jpg"

    product.add_image(image_url)
    product.add_image(image_url)

    assert len(product.images) == 1


def test_primary_image_returns_lowest_position() -> None:
    """Galvenais attēls ir attēls ar mazāko pozīcijas numuru."""

    product = Product(
        brand="Weber",
        sku="1500186",
    )

    product.add_image(
        url="https://example.com/second.jpg",
        position=2,
    )
    product.add_image(
        url="https://example.com/first.jpg",
        position=1,
    )

    assert product.primary_image is not None
    assert (
        product.primary_image.url
        == "https://example.com/first.jpg"
    )


def test_primary_image_is_none_when_no_images_exist() -> None:
    """Ja attēlu nav, galvenais attēls ir None."""

    product = Product(
        brand="Weber",
        sku="1500186",
    )

    assert product.primary_image is None