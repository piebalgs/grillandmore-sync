"""Tests for the Weber product-series scoring rule."""

from src.descriptions.matching.constants import SERIES_POINTS
from src.descriptions.matching.models import (
    DescriptionProduct,
    SupplierProduct,
)
from src.descriptions.matching.rules.series import (
    RULE_NAME,
    find_series,
    score_series,
)


def test_series_rule_has_stable_configuration() -> None:
    assert RULE_NAME == "SERIES"
    assert SERIES_POINTS == 20.0


def test_find_series_returns_none_for_none() -> None:
    assert find_series(None) is None


def test_find_series_returns_none_for_empty_text() -> None:
    assert find_series("") is None
    assert find_series("   ") is None


def test_find_series_returns_none_for_unknown_text() -> None:
    assert find_series("Premium protective cover") is None


def test_find_series_detects_spirit() -> None:
    assert find_series("Weber Spirit EP-425") == "SPIRIT"


def test_find_series_detects_genesis_case_insensitively() -> None:
    assert find_series("weber genesis e-335") == "GENESIS"


def test_find_series_detects_series_in_compact_text() -> None:
    assert find_series("SPIRIT_EP_425") == "SPIRIT"


def test_find_series_detects_smokey_mountain() -> None:
    assert (
        find_series("Weber Smokey Mountain Cooker 47 cm")
        == "SMOKEY MOUNTAIN"
    )


def test_find_series_detects_smokey_joe() -> None:
    assert find_series("Smokey Joe Premium 37 cm") == "SMOKEY JOE"


def test_find_series_detects_master_touch_with_hyphen() -> None:
    assert (
        find_series("Weber Master-Touch GBS E-5750")
        == "MASTER TOUCH"
    )


def test_find_series_detects_go_anywhere_with_hyphen() -> None:
    assert (
        find_series("Weber Go-Anywhere charcoal grill")
        == "GO ANYWHERE"
    )


def test_find_series_detects_q_series() -> None:
    assert find_series("Weber Q 2200 gas grill") == "Q"


def test_score_series_awards_full_points_for_match() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    item = score_series(description, supplier)

    assert item.rule == "SERIES"
    assert item.points == 20.0
    assert item.maximum == 20.0
    assert item.is_full_match is True
    assert item.reason == "Series matches: SPIRIT"


def test_score_series_uses_barbecue_code_first() -> None:
    description = DescriptionProduct(
        description_key="GENESIS_E_335",
        barbecue_code="SPIRIT EP-425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    item = score_series(description, supplier)

    assert item.points == SERIES_POINTS
    assert item.reason == "Series matches: SPIRIT"


def test_score_series_reports_mismatch() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    supplier = SupplierProduct(
        sku="1500100",
        name="Weber Genesis E-335",
    )

    item = score_series(description, supplier)

    assert item.points == 0.0
    assert item.maximum == SERIES_POINTS
    assert item.reason == "Series mismatch: SPIRIT vs GENESIS"


def test_score_series_reports_missing_description_series() -> None:
    description = DescriptionProduct(
        description_key="UNKNOWN_PRODUCT",
    )
    supplier = SupplierProduct(
        sku="1500100",
        name="Weber Genesis E-335",
    )

    item = score_series(description, supplier)

    assert item.points == 0.0
    assert item.reason == "Description series could not be determined"


def test_score_series_reports_missing_supplier_series() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    supplier = SupplierProduct(
        sku="7182",
        name="Premium protective cover",
    )

    item = score_series(description, supplier)

    assert item.points == 0.0
    assert item.reason == "Supplier series could not be determined"


def test_score_series_reports_when_neither_series_is_known() -> None:
    description = DescriptionProduct(
        description_key="UNKNOWN_PRODUCT",
    )
    supplier = SupplierProduct(
        sku="7182",
        name="Premium protective cover",
    )

    item = score_series(description, supplier)

    assert item.points == 0.0
    assert item.reason == (
        "Series could not be determined for either product"
    )
