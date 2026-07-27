"""Tests for the EAN matching expert."""

import pytest

from src.descriptions.matching.models import (
    DescriptionProduct,
    SupplierProduct,
)
from src.descriptions.matching.rules.ean import (
    MAXIMUM_POINTS,
    normalize_barcode,
    score_ean,
)
from src.descriptions.matching.score_models import RuleStatus


def description(barcode=""):
    return DescriptionProduct(
        description_key="SPIRIT_E_435",
        title="Spirit E-435",
        barcode=barcode,
    )


def supplier(barcode=""):
    return SupplierProduct(
        sku="1502117",
        name="Weber Spirit E-435",
        barcode=barcode,
        producer="Weber",
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0077924920172", "0077924920172"),
        ("77924920172.0", "77924920172"),
        (" 0077 9249 2017 2 ", "0077924920172"),
        ("EAN: 0077924920172", "0077924920172"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_barcode(raw, expected):
    assert normalize_barcode(raw) == expected


def test_identical_ean_is_match():
    result = score_ean(
        description("0077924920172"),
        supplier("0077924920172"),
    )

    assert result.rule == "EAN"
    assert result.status is RuleStatus.MATCH
    assert result.points == MAXIMUM_POINTS
    assert result.maximum == MAXIMUM_POINTS


@pytest.mark.parametrize(
    ("description_ean", "supplier_ean"),
    [
        ("", "0077924920172"),
        ("0077924920172", ""),
        ("", ""),
    ],
)
def test_missing_ean_is_unknown(description_ean, supplier_ean):
    result = score_ean(
        description(description_ean),
        supplier(supplier_ean),
    )

    assert result.status is RuleStatus.UNKNOWN
    assert result.points == 0
    assert "unavailable" in result.reason


def test_different_ean_is_conflict():
    result = score_ean(
        description("0077924920172"),
        supplier("0077924920813"),
    )

    assert result.status is RuleStatus.CONFLICT
    assert result.points == 0
    assert "conflict" in result.reason
