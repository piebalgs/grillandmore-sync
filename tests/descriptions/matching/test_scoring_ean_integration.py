"""Integration tests for the opt-in EAN matching rule."""

from src.descriptions.matching.models import (
    DescriptionProduct,
    SupplierProduct,
)
from src.descriptions.matching.rules import score_ean
from src.descriptions.matching.score_models import RuleStatus
from src.descriptions.matching.scoring import (
    DEFAULT_RULES,
    calculate_score,
)


def test_default_rules_remain_backward_compatible():
    assert [rule.__name__ for rule in DEFAULT_RULES] == [
        "score_model_code",
        "score_series",
        "score_producer",
        "score_title_similarity",
    ]


def test_ean_can_be_added_explicitly_before_default_rules():
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
        barcode="0077924000001",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
        barcode="0077924000001",
        producer="Weber",
    )

    result = calculate_score(
        description,
        supplier,
        rules=(score_ean, *DEFAULT_RULES),
    )

    assert result.items[0].rule == "EAN"
    assert result.items[0].status is RuleStatus.MATCH
    assert len(result.items) == 5


def test_missing_ean_does_not_dilute_existing_confidence():
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
        producer="Weber",
    )

    baseline = calculate_score(description, supplier)
    with_ean = calculate_score(
        description,
        supplier,
        rules=(score_ean, *DEFAULT_RULES),
    )

    assert with_ean.get_item("EAN").status is RuleStatus.UNKNOWN
    assert with_ean.total == baseline.total
    assert with_ean.maximum == baseline.maximum
    assert with_ean.confidence == baseline.confidence


def test_ean_conflict_reduces_explicit_combined_confidence():
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
        barcode="0077924000001",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
        barcode="0077924000002",
        producer="Weber",
    )

    baseline = calculate_score(description, supplier)
    with_ean = calculate_score(
        description,
        supplier,
        rules=(score_ean, *DEFAULT_RULES),
    )

    assert with_ean.get_item("EAN").status is RuleStatus.CONFLICT
    assert with_ean.total == baseline.total
    assert with_ean.maximum == baseline.maximum + 100
    assert with_ean.confidence < baseline.confidence
