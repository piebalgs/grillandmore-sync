"""Tests for product matching data models."""

import pytest

from src.descriptions.matching.models import (
    DescriptionProduct,
    MatchCandidate,
    MatchResult,
    MatchStatus,
    SupplierProduct,
)


def test_description_product_normalizes_title() -> None:
    product = DescriptionProduct(
        description_key="SPIRIT_EP_425",
        title="Weber Spirit EP-425 Gāzes grils, melns",
        series="Spirit",
        barbecue_code="SPIRIT_EP_425",
    )

    assert product.description_key == "SPIRIT_EP_425"
    assert product.normalized_name == "weber spirit ep 425"


def test_description_product_strips_text_fields() -> None:
    product = DescriptionProduct(
        description_key="  SPIRIT_EP_425  ",
        title="  Spirit EP-425  ",
        title_line_1="  Spirit gas grill  ",
        series="  Spirit  ",
        barbecue_code="  SPIRIT_EP_425  ",
    )

    assert product.description_key == "SPIRIT_EP_425"
    assert product.title == "Spirit EP-425"
    assert product.title_line_1 == "Spirit gas grill"
    assert product.series == "Spirit"
    assert product.barbecue_code == "SPIRIT_EP_425"


def test_description_product_uses_title_line_1_as_fallback() -> None:
    product = DescriptionProduct(
        description_key="GENESIS_E_335",
        title_line_1="Weber Genesis E-335",
    )

    assert product.normalized_name == "weber genesis e 335"


def test_description_product_uses_barbecue_code_as_fallback() -> None:
    product = DescriptionProduct(
        description_key="SPIRIT_EP_425",
        barbecue_code="SPIRIT_EP_425",
    )

    assert product.normalized_name == "spirit ep 425"


def test_description_product_uses_description_key_as_last_fallback() -> None:
    product = DescriptionProduct(
        description_key="GENESIS_E_335",
    )

    assert product.normalized_name == "genesis e 335"


def test_description_product_requires_description_key() -> None:
    with pytest.raises(
        ValueError,
        match="description_key must not be empty",
    ):
        DescriptionProduct(
            description_key="   ",
            title="Spirit EP-425",
        )


def test_supplier_product_normalizes_name() -> None:
    product = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425 Gāzes grils, melns",
        barcode="0077924000000",
        producer="WEBER",
    )

    assert product.sku == "1500013"
    assert product.normalized_name == "weber spirit ep 425"


def test_supplier_product_strips_text_fields() -> None:
    product = SupplierProduct(
        sku="  1500013  ",
        name="  Spirit EP-425  ",
        barcode="  0077924000000  ",
        producer="  WEBER  ",
    )

    assert product.sku == "1500013"
    assert product.name == "Spirit EP-425"
    assert product.barcode == "0077924000000"
    assert product.producer == "WEBER"


def test_supplier_product_requires_sku() -> None:
    with pytest.raises(
        ValueError,
        match="sku must not be empty",
    ):
        SupplierProduct(
            sku="   ",
            name="Spirit EP-425",
        )


def test_supplier_product_requires_name() -> None:
    with pytest.raises(
        ValueError,
        match="name must not be empty",
    ):
        SupplierProduct(
            sku="1500013",
            name="   ",
        )


def test_match_candidate_normalizes_values() -> None:
    supplier = SupplierProduct(
        sku="1500013",
        name="Spirit EP-425",
    )

    candidate = MatchCandidate(
        supplier=supplier,
        confidence="97.5",
        reasons=[
            " Model matches ",
            "Series matches",
            "",
        ],
        match_type=" fuzzy ",
    )

    assert candidate.confidence == 97.5
    assert candidate.reasons == (
        "Model matches",
        "Series matches",
    )
    assert candidate.match_type == "FUZZY"


@pytest.mark.parametrize(
    "confidence",
    [
        -0.1,
        100.1,
        150,
    ],
)
def test_match_candidate_rejects_invalid_confidence(
    confidence: float,
) -> None:
    supplier = SupplierProduct(
        sku="1500013",
        name="Spirit EP-425",
    )

    with pytest.raises(
        ValueError,
        match="confidence must be between 0 and 100",
    ):
        MatchCandidate(
            supplier=supplier,
            confidence=confidence,
        )


def test_match_result_returns_highest_confidence_candidate() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
        title="Spirit EP-425",
    )

    lower_candidate = MatchCandidate(
        supplier=SupplierProduct(
            sku="1500014",
            name="Spirit EP-425 Stealth",
        ),
        confidence=88.0,
    )

    higher_candidate = MatchCandidate(
        supplier=SupplierProduct(
            sku="1500013",
            name="Spirit EP-425",
        ),
        confidence=98.0,
    )

    result = MatchResult(
        description=description,
        candidates=[
            lower_candidate,
            higher_candidate,
        ],
        status=MatchStatus.AUTO,
    )

    assert result.best_candidate is higher_candidate
    assert result.best_candidate.supplier.sku == "1500013"


def test_match_result_without_candidates_has_no_best_candidate() -> None:
    description = DescriptionProduct(
        description_key="UNKNOWN_MODEL",
        title="Unknown model",
    )

    result = MatchResult(
        description=description,
    )

    assert result.best_candidate is None
    assert result.status is MatchStatus.UNMATCHED
    assert result.is_matched is False


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("AUTO", MatchStatus.AUTO),
        ("auto", MatchStatus.AUTO),
        ("REVIEW", MatchStatus.REVIEW),
        ("manual", MatchStatus.MANUAL),
        ("UNMATCHED", MatchStatus.UNMATCHED),
    ],
)
def test_match_result_accepts_status_as_string(
    status: str,
    expected: MatchStatus,
) -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
        title="Spirit EP-425",
    )

    result = MatchResult(
        description=description,
        status=status,
    )

    assert result.status is expected


def test_match_result_rejects_unknown_status() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
        title="Spirit EP-425",
    )

    with pytest.raises(
        ValueError,
        match="Unknown match status",
    ):
        MatchResult(
            description=description,
            status="INVALID",
        )


def test_auto_result_with_candidate_is_matched() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
        title="Spirit EP-425",
    )

    candidate = MatchCandidate(
        supplier=SupplierProduct(
            sku="1500013",
            name="Spirit EP-425",
        ),
        confidence=99.0,
    )

    result = MatchResult(
        description=description,
        candidates=[candidate],
        status=MatchStatus.AUTO,
    )

    assert result.is_matched is True


def test_manual_result_with_candidate_is_matched() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
        title="Spirit EP-425",
    )

    candidate = MatchCandidate(
        supplier=SupplierProduct(
            sku="1500013",
            name="Spirit EP-425",
        ),
        confidence=70.0,
    )

    result = MatchResult(
        description=description,
        candidates=[candidate],
        status=MatchStatus.MANUAL,
    )

    assert result.is_matched is True


def test_review_result_is_not_yet_matched() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
        title="Spirit EP-425",
    )

    candidate = MatchCandidate(
        supplier=SupplierProduct(
            sku="1500013",
            name="Spirit EP-425",
        ),
        confidence=89.0,
    )

    result = MatchResult(
        description=description,
        candidates=[candidate],
        status=MatchStatus.REVIEW,
    )

    assert result.best_candidate is candidate
    assert result.is_matched is False


def test_match_result_strips_note() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )

    result = MatchResult(
        description=description,
        note="  Needs manual review  ",
    )

    assert result.note == "Needs manual review"
