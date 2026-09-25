"""Tests for Weber grill target selection."""

from src.descriptions.matching.grill_target_selector import (
    select_grill_targets,
)
from src.descriptions.parser import ProductDescription


def test_select_grill_targets_uses_description_for_precise_q_model():
    source = ProductDescription(
        sku="WEBERQ_3200_BL",
        import_id="WEBER_Q3200",
        title="Weber Q 3200 w/cart Gas Grill",
        title_line_1="Weber Q 3200",
        source_description=(
            "Enjoy the ultimate backyard grilling experience "
            "with the powerful Q3200N+ Gas Grill with Premium Cart."
        ),
    )

    products = (
        {
            "id": 101,
            "sku": "1501200",
            "name": "Gāzes grils Weber Q3200N+",
            "categories": [{"id": 422}, {"id": 247}],
        },
        {
            "id": 102,
            "sku": "3400854",
            "name": "Q3200N+ COVER EMEA",
            "categories": [{"id": 422}, {"id": 247}, {"id": 458}],
        },
    )

    targets = select_grill_targets(
        product=source,
        woo_products=products,
    )

    assert tuple(target["sku"] for target in targets) == (
        "1501200",
    )


def test_select_grill_targets_can_return_multiple_valid_woo_products():
    source = ProductDescription(
        sku="WEBERQ_1200N_BL",
        import_id="WEBER_Q1200N",
        title="Weber Q 1200N Gas Grill",
        source_description="Weber Q1200N Gas Grill.",
    )

    products = (
        {
            "id": 201,
            "sku": "1501071",
            "name": "Gāzes grils Weber Q1200N",
            "categories": [{"id": 422}, {"id": 247}],
        },
        {
            "id": 202,
            "sku": "1501086",
            "name": "Gāzes grils Weber Q1200N ar statīvu",
            "categories": [{"id": 422}, {"id": 247}],
        },
    )

    targets = select_grill_targets(
        product=source,
        woo_products=products,
    )

    assert tuple(target["sku"] for target in targets) == (
        "1501071",
        "1501086",
    )


def test_select_grill_targets_returns_empty_for_missing_model():
    source = ProductDescription(
        sku="SUMMIT_FS38X_S",
        import_id="SUMMIT_FS38X_S",
        title="Summit FS38X S Gas Grill",
        source_description="Summit FS38X S Gas Grill.",
    )

    products = (
        {
            "id": 301,
            "sku": "1500178",
            "name": "Gāzes grils Summit FS38X E Smart",
            "categories": [{"id": 422}, {"id": 247}],
        },
        {
            "id": 302,
            "sku": "1500099",
            "name": "Gāzes grils Summit FS38 S",
            "categories": [{"id": 422}, {"id": 247}],
        },
    )

    targets = select_grill_targets(
        product=source,
        woo_products=products,
    )

    assert targets == ()
def test_select_grill_targets_returns_empty_when_source_model_is_unknown():
    source = ProductDescription(
        sku="UNKNOWN_PRODUCT",
        import_id="UNKNOWN_PRODUCT",
        title="Weber Gas Grill",
        title_line_1="Gas Grill",
        source_description="A gas grill for outdoor cooking.",
    )

    products = (
        {
            "id": 401,
            "sku": "1501071",
            "name": "Gāzes grils Weber Q1200N",
            "categories": [{"id": 422}, {"id": 247}],
        },
    )

    targets = select_grill_targets(
        product=source,
        woo_products=products,
    )

    assert targets == ()