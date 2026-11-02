
import pytest

from src.descriptions.models import FormattedProduct
from src.descriptions.target_configuration import (
    apply_target_configuration,
)


def make_product(sku="1501086"):
    return FormattedProduct(
        sku=sku,
        title="Weber Q1200N",
        short_description="<p>Īsais apraksts.</p>",
        description_html="<p>Pilnais apraksts.</p>",
    )


def test_stand_configuration_is_added():
    product = make_product()

    result = apply_target_configuration(
        product=product,
        target_sku="1501086",
    )

    assert "<h2>Komplektācija</h2>" in result.description_html
    assert "grils un statīvs" in result.description_html
    assert result.sku == "1501086"


def test_regular_grill_remains_unchanged():
    product = make_product("1501071")

    result = apply_target_configuration(
        product=product,
        target_sku="1501071",
    )

    assert result == product
    assert "Komplektācija" not in result.description_html


def test_original_product_is_not_modified():
    product = make_product()
    original_html = product.description_html

    apply_target_configuration(
        product=product,
        target_sku="1501086",
    )

    assert product.description_html == original_html


def test_configuration_cannot_be_added_twice():
    product = make_product()

    configured = apply_target_configuration(
        product=product,
        target_sku="1501086",
    )

    with pytest.raises(ValueError, match="komplektācijas sadaļa"):
        apply_target_configuration(
            product=configured,
            target_sku="1501086",
        )


def test_rejects_mismatched_sku():
    product = make_product()

    with pytest.raises(ValueError, match="SKU nesakrīt"):
        apply_target_configuration(
            product=product,
            target_sku="1501071",
        )


def test_rejects_empty_sku():
    product = make_product()

    with pytest.raises(ValueError, match="target_sku"):
        apply_target_configuration(
            product=product,
            target_sku=" ",
        )
