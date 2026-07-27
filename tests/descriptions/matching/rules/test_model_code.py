"""Tests for the model-code scoring rule."""

from src.descriptions.matching.models import (
    DescriptionProduct,
    SupplierProduct,
)
from src.descriptions.matching.rules.model_code import (
    MAXIMUM_POINTS,
    RULE_NAME,
    score_model_code,
)


def test_model_code_rule_has_stable_configuration() -> None:
    assert RULE_NAME == "MODEL_CODE"
    assert MAXIMUM_POINTS == 50.0


def test_scores_exact_barbecue_code_match() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
        barbecue_code="SPIRIT_EP_425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    item = score_model_code(description, supplier)

    assert item.rule == "MODEL_CODE"
    assert item.points == 50.0
    assert item.maximum == 50.0
    assert item.is_full_match is True
    assert "matches" in item.reason.lower()


def test_scores_description_key_when_barbecue_code_is_empty() -> None:
    description = DescriptionProduct(
        description_key="GENESIS_E_335",
    )
    supplier = SupplierProduct(
        sku="1500100",
        name="Weber Genesis E-335 gāzes grils",
    )

    item = score_model_code(description, supplier)

    assert item.points == 50.0


def test_matches_different_model_code_separators() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
        barbecue_code="EP-425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP425",
    )

    item = score_model_code(description, supplier)

    assert item.points == 50.0


def test_matches_lowercase_supplier_name() -> None:
    description = DescriptionProduct(
        description_key="GENESIS_E_335",
    )
    supplier = SupplierProduct(
        sku="1500100",
        name="weber genesis e-335",
    )

    item = score_model_code(description, supplier)

    assert item.points == 50.0


def test_matches_model_code_inside_long_supplier_name() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
        barbecue_code="EP-425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name=(
            "Weber Spirit EP-425 četru degļu gāzes grils ar sānu degli"
        ),
    )

    item = score_model_code(description, supplier)

    assert item.points == 50.0


def test_returns_zero_when_model_code_does_not_match() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
        barbecue_code="EP-425",
    )
    supplier = SupplierProduct(
        sku="1500100",
        name="Weber Genesis E-335",
    )

    item = score_model_code(description, supplier)

    assert item.points == 0.0
    assert item.maximum == 50.0
    assert item.is_full_match is False
    assert item.reason == "Model code did not match"


def test_description_key_can_match_complete_model_group() -> None:
    description = DescriptionProduct(
        description_key="GENESIS_E_335",
    )
    supplier = SupplierProduct(
        sku="1500100",
        name="Genesis E-335",
    )

    item = score_model_code(description, supplier)

    assert item.points == 50.0


def test_barbecue_code_is_checked_before_description_key() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT",
        barbecue_code="EP-425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    item = score_model_code(description, supplier)

    assert item.points == 50.0
    assert "ep425" in item.reason.lower()


def test_duplicate_model_values_do_not_affect_result() -> None:
    description = DescriptionProduct(
        description_key="EP-425",
        barbecue_code="EP425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    item = score_model_code(description, supplier)

    assert item.points == 50.0
