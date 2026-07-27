"""Tests for the producer scoring rule."""

from src.descriptions.matching.constants import PRODUCER_POINTS
from src.descriptions.matching.models import (
    DescriptionProduct,
    SupplierProduct,
)
from src.descriptions.matching.rules.producer import (
    EXPECTED_PRODUCER,
    RULE_NAME,
    _is_expected_producer,
    _normalize_producer,
    _producer_tokens,
    score_producer,
)


def make_description() -> DescriptionProduct:
    """Return a valid Weber description record for producer-rule tests."""
    return DescriptionProduct(
        description_key="SPIRIT_EP_425",
        title="Weber Spirit EP-425",
    )


def test_producer_rule_has_stable_configuration() -> None:
    assert RULE_NAME == "PRODUCER"
    assert EXPECTED_PRODUCER == "WEBER"
    assert PRODUCER_POINTS == 5.0


def test_normalize_producer_returns_empty_for_none() -> None:
    assert _normalize_producer(None) == ""


def test_normalize_producer_returns_empty_for_empty_text() -> None:
    assert _normalize_producer("") == ""
    assert _normalize_producer("   ") == ""


def test_normalize_producer_is_case_insensitive() -> None:
    assert _normalize_producer("Weber") == "weber"
    assert _normalize_producer("WEBER") == "weber"


def test_producer_tokens_normalize_multiple_words() -> None:
    assert _producer_tokens("WEBER aksesuāri") == (
        "weber",
        "aksesuāri",
    )


def test_expected_producer_matches_exact_weber() -> None:
    assert _is_expected_producer("WEBER") is True


def test_expected_producer_matches_case_insensitively() -> None:
    assert _is_expected_producer("Weber") is True
    assert _is_expected_producer("weber") is True


def test_expected_producer_matches_weber_accessories() -> None:
    assert _is_expected_producer("WEBER aksesuāri") is True


def test_expected_producer_does_not_match_other_brand() -> None:
    assert _is_expected_producer("Napoleon") is False


def test_expected_producer_does_not_match_partial_word() -> None:
    assert _is_expected_producer("Weberman") is False


def test_expected_producer_does_not_match_empty_value() -> None:
    assert _is_expected_producer("") is False
    assert _is_expected_producer(None) is False


def test_score_producer_awards_full_points_for_weber() -> None:
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
        producer="WEBER",
    )

    item = score_producer(make_description(), supplier)

    assert item.rule == RULE_NAME
    assert item.points == PRODUCER_POINTS
    assert item.maximum == PRODUCER_POINTS
    assert item.is_full_match is True
    assert item.reason == "Producer matches: WEBER"


def test_score_producer_accepts_weber_accessories_group() -> None:
    supplier = SupplierProduct(
        sku="7032",
        name="Weber Traveler griešanas dēlis ar tvertni",
        producer="WEBER aksesuāri",
    )

    item = score_producer(make_description(), supplier)

    assert item.points == PRODUCER_POINTS
    assert item.reason == "Producer matches: WEBER"


def test_score_producer_accepts_lowercase_weber() -> None:
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
        producer="weber",
    )

    item = score_producer(make_description(), supplier)

    assert item.points == PRODUCER_POINTS


def test_score_producer_returns_zero_for_missing_producer() -> None:
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    item = score_producer(make_description(), supplier)

    assert item.points == 0.0
    assert item.maximum == PRODUCER_POINTS
    assert item.is_full_match is False
    assert item.reason == (
        "Supplier producer could not be determined"
    )


def test_score_producer_returns_zero_for_other_brand() -> None:
    supplier = SupplierProduct(
        sku="P500RSIBPK-3-PHM",
        name="Napoleon Prestige 500",
        producer="Napoleon",
    )

    item = score_producer(make_description(), supplier)

    assert item.points == 0.0
    assert item.maximum == PRODUCER_POINTS
    assert item.is_full_match is False
    assert item.reason == (
        "Producer mismatch: WEBER vs Napoleon"
    )


def test_score_producer_does_not_use_supplier_name_as_fallback() -> None:
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
        producer="",
    )

    item = score_producer(make_description(), supplier)

    assert item.points == 0.0
    assert item.reason == (
        "Supplier producer could not be determined"
    )
