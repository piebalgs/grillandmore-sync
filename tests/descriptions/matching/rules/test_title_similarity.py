"""Tests for the title-similarity scoring rule."""

from __future__ import annotations

import pytest

from src.descriptions.matching.models import (
    DescriptionProduct,
    SupplierProduct,
)
from src.descriptions.matching.rules import title_similarity
from src.descriptions.matching.rules.title_similarity import (
    MAXIMUM_POINTS,
    MINIMUM_SIMILARITY,
    RULE_NAME,
    calculate_title_similarity,
    score_title_similarity,
    similarity_to_points,
)


def make_description(
    *,
    title: str = "Weber Spirit EP-425 gāzes grils",
) -> DescriptionProduct:
    return DescriptionProduct(
        description_key="SPIRIT_EP_425",
        title=title,
    )


def make_supplier(
    *,
    name: str = "Weber Spirit EP-425 gāzes grils",
) -> SupplierProduct:
    return SupplierProduct(
        sku="1500013",
        name=name,
    )


def test_constants_are_stable() -> None:
    assert RULE_NAME == "TITLE_SIMILARITY"
    assert MAXIMUM_POINTS == 25.0
    assert MINIMUM_SIMILARITY == 60.0


def test_identical_titles_have_full_similarity() -> None:
    similarity = calculate_title_similarity(
        make_description(),
        make_supplier(),
    )

    assert similarity == 100.0


def test_normalized_titles_are_compared() -> None:
    description = make_description(
        title="  Weber SPIRIT EP-425 — gāzes grils  ",
    )
    supplier = make_supplier(
        name="weber spirit ep 425 gazes grils",
    )

    similarity = calculate_title_similarity(
        description,
        supplier,
    )

    assert similarity == 100.0


def test_different_titles_have_lower_similarity() -> None:
    similarity = calculate_title_similarity(
        make_description(
            title="Weber Spirit EP-425 gāzes grils",
        ),
        make_supplier(
            name="Weber Genesis E-335 gāzes grils",
        ),
    )

    assert 0.0 <= similarity < 100.0


@pytest.mark.parametrize(
    ("similarity", "expected_points"),
    [
        (100.0, 25.0),
        (90.0, 22.5),
        (80.0, 20.0),
        (60.0, 15.0),
        (59.99, 0.0),
        (0.0, 0.0),
    ],
)
def test_similarity_is_converted_to_points(
    similarity: float,
    expected_points: float,
) -> None:
    assert similarity_to_points(similarity) == expected_points


def test_similarity_is_limited_to_valid_range() -> None:
    assert similarity_to_points(150.0) == 25.0
    assert similarity_to_points(-10.0) == 0.0


def test_exact_title_match_receives_maximum_points() -> None:
    result = score_title_similarity(
        make_description(),
        make_supplier(),
    )

    assert result.rule == "TITLE_SIMILARITY"
    assert result.points == 25.0
    assert result.maximum == 25.0
    assert result.reason == "Title similarity: 100.0%"


def test_similarity_above_threshold_receives_proportional_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        title_similarity.fuzz,
        "WRatio",
        lambda *args, **kwargs: 80.0,
    )

    result = score_title_similarity(
        make_description(),
        make_supplier(),
    )

    assert result.points == 20.0
    assert result.maximum == 25.0
    assert result.reason == "Title similarity: 80.0%"


def test_similarity_below_threshold_receives_zero_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        title_similarity.fuzz,
        "WRatio",
        lambda *args, **kwargs: 59.9,
    )

    result = score_title_similarity(
        make_description(),
        make_supplier(),
    )

    assert result.points == 0.0
    assert result.maximum == 25.0
    assert result.reason == (
        "Title similarity is below the minimum threshold: 59.9%"
    )


def test_rapidfuzz_does_not_repeat_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_arguments: dict[str, object] = {}

    def fake_wratio(
        first: str,
        second: str,
        *,
        processor: object,
    ) -> float:
        captured_arguments["first"] = first
        captured_arguments["second"] = second
        captured_arguments["processor"] = processor
        return 75.0

    monkeypatch.setattr(
        title_similarity.fuzz,
        "WRatio",
        fake_wratio,
    )

    description = make_description(
        title="Weber SPIRIT EP-425",
    )
    supplier = make_supplier(
        name="weber spirit ep 425",
    )

    calculate_title_similarity(
        description,
        supplier,
    )

    assert captured_arguments == {
        "first": description.normalized_name,
        "second": supplier.normalized_name,
        "processor": None,
    }