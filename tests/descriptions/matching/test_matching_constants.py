"""Tests for product-matching scoring constants."""

from src.descriptions.matching.constants import (
    MODEL_CODE_POINTS,
    PRODUCER_POINTS,
    SERIES_POINTS,
    TITLE_POINTS,
)


def test_scoring_points_have_expected_values() -> None:
    assert MODEL_CODE_POINTS == 50.0
    assert SERIES_POINTS == 20.0
    assert TITLE_POINTS == 25.0
    assert PRODUCER_POINTS == 5.0


def test_scoring_points_are_numeric() -> None:
    values = (
        MODEL_CODE_POINTS,
        SERIES_POINTS,
        TITLE_POINTS,
        PRODUCER_POINTS,
    )

    assert all(
        isinstance(value, (int, float))
        for value in values
    )


def test_scoring_points_are_positive() -> None:
    values = (
        MODEL_CODE_POINTS,
        SERIES_POINTS,
        TITLE_POINTS,
        PRODUCER_POINTS,
    )

    assert all(value > 0 for value in values)


def test_scoring_points_total_one_hundred() -> None:
    total = (
        MODEL_CODE_POINTS
        + SERIES_POINTS
        + TITLE_POINTS
        + PRODUCER_POINTS
    )

    assert total == 100.0


def test_model_code_has_highest_weight() -> None:
    assert MODEL_CODE_POINTS > SERIES_POINTS
    assert MODEL_CODE_POINTS > TITLE_POINTS
    assert MODEL_CODE_POINTS > PRODUCER_POINTS


def test_producer_has_lowest_weight() -> None:
    assert PRODUCER_POINTS < MODEL_CODE_POINTS
    assert PRODUCER_POINTS < SERIES_POINTS
    assert PRODUCER_POINTS < TITLE_POINTS
