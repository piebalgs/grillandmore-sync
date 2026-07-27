"""Tests for the product-match scoring coordinator."""

from src.descriptions.matching.models import (
    DescriptionProduct,
    SupplierProduct,
)
from src.descriptions.matching.score_models import ScoreItem
from src.descriptions.matching.scoring import (
    DEFAULT_RULES,
    calculate_score,
)


def test_default_rules_contain_model_code_rule() -> None:
    assert len(DEFAULT_RULES) == 1
    assert DEFAULT_RULES[0].__name__ == "score_model_code"


def test_calculate_score_executes_default_rules() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    result = calculate_score(description, supplier)

    assert len(result.items) == 1
    assert result.items[0].rule == "MODEL_CODE"
    assert result.total == 50.0
    assert result.maximum == 50.0
    assert result.confidence == 100.0


def test_calculate_score_returns_zero_for_non_match() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    supplier = SupplierProduct(
        sku="1500100",
        name="Weber Genesis E-335",
    )

    result = calculate_score(description, supplier)

    assert result.total == 0.0
    assert result.maximum == 50.0
    assert result.confidence == 0.0


def test_calculate_score_accepts_custom_rules() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    def custom_rule(
        description: DescriptionProduct,
        supplier: SupplierProduct,
    ) -> ScoreItem:
        del description
        del supplier

        return ScoreItem(
            rule="CUSTOM",
            points=5,
            maximum=10,
            reason="Custom rule awarded half points",
        )

    result = calculate_score(
        description,
        supplier,
        rules=(custom_rule,),
    )

    assert len(result.items) == 1
    assert result.items[0].rule == "CUSTOM"
    assert result.total == 5.0
    assert result.maximum == 10.0
    assert result.confidence == 50.0


def test_calculate_score_accepts_rule_generator() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    def first_rule(
        description: DescriptionProduct,
        supplier: SupplierProduct,
    ) -> ScoreItem:
        del description
        del supplier

        return ScoreItem(
            rule="FIRST",
            points=10,
            maximum=10,
            reason="First rule matched",
        )

    def second_rule(
        description: DescriptionProduct,
        supplier: SupplierProduct,
    ) -> ScoreItem:
        del description
        del supplier

        return ScoreItem(
            rule="SECOND",
            points=5,
            maximum=10,
            reason="Second rule partially matched",
        )

    result = calculate_score(
        description,
        supplier,
        rules=(
            rule
            for rule in (
                first_rule,
                second_rule,
            )
        ),
    )

    assert len(result.items) == 2
    assert result.total == 15.0
    assert result.maximum == 20.0
    assert result.confidence == 75.0


def test_calculate_score_accepts_empty_rule_collection() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    result = calculate_score(
        description,
        supplier,
        rules=(),
    )

    assert result.is_empty is True
    assert result.total == 0.0
    assert result.maximum == 0.0
    assert result.confidence == 0.0
