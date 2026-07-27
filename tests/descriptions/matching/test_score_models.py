"""Tests for explainable scoring data models."""

import pytest

from src.descriptions.matching.score_models import (
    RuleStatus,
    ScoreItem,
    ScoreResult,
)


def test_score_item_normalizes_values() -> None:
    item = ScoreItem(
        rule=" model_code ",
        points=50,
        maximum=50,
        reason=" Exact model code match ",
    )

    assert item.rule == "MODEL_CODE"
    assert item.points == 50.0
    assert item.maximum == 50.0
    assert item.reason == "Exact model code match"


def test_score_item_calculates_ratio_and_percentage() -> None:
    item = ScoreItem(
        rule="TITLE",
        points=15,
        maximum=20,
        reason="Title similarity",
    )

    assert item.ratio == 0.75
    assert item.percentage == 75.0


def test_score_item_identifies_full_match() -> None:
    item = ScoreItem(
        rule="SERIES",
        points=20,
        maximum=20,
        reason="Series matches",
    )

    assert item.is_full_match is True
    assert item.has_points is True


def test_score_item_identifies_zero_score() -> None:
    item = ScoreItem(
        rule="PRODUCER",
        points=0,
        maximum=5,
        reason="Producer did not match",
    )

    assert item.is_full_match is False
    assert item.has_points is False
    assert item.percentage == 0.0


def test_score_item_is_immutable() -> None:
    item = ScoreItem(
        rule="MODEL_CODE",
        points=50,
        maximum=50,
        reason="Model code matches",
    )

    with pytest.raises(AttributeError):
        item.points = 10


def test_score_item_requires_rule() -> None:
    with pytest.raises(
        ValueError,
        match="rule must not be empty",
    ):
        ScoreItem(
            rule="   ",
            points=5,
            maximum=5,
            reason="Matched",
        )


def test_score_item_requires_reason() -> None:
    with pytest.raises(
        ValueError,
        match="reason must not be empty",
    ):
        ScoreItem(
            rule="PRODUCER",
            points=5,
            maximum=5,
            reason="   ",
        )


@pytest.mark.parametrize(
    "maximum",
    [
        0,
        -1,
        -10.5,
    ],
)
def test_score_item_requires_positive_maximum(
    maximum: float,
) -> None:
    with pytest.raises(
        ValueError,
        match="maximum must be greater than 0",
    ):
        ScoreItem(
            rule="TITLE",
            points=0,
            maximum=maximum,
            reason="Invalid maximum",
        )


def test_score_item_rejects_negative_points() -> None:
    with pytest.raises(
        ValueError,
        match="points must not be negative",
    ):
        ScoreItem(
            rule="TITLE",
            points=-1,
            maximum=20,
            reason="Invalid score",
        )


def test_score_item_rejects_points_above_maximum() -> None:
    with pytest.raises(
        ValueError,
        match="points must not exceed maximum",
    ):
        ScoreItem(
            rule="TITLE",
            points=21,
            maximum=20,
            reason="Invalid score",
        )


def test_score_result_calculates_totals_and_confidence() -> None:
    result = ScoreResult(
        items=(
            ScoreItem(
                rule="MODEL_CODE",
                points=50,
                maximum=50,
                reason="Model code matches",
            ),
            ScoreItem(
                rule="SERIES",
                points=20,
                maximum=20,
                reason="Series matches",
            ),
            ScoreItem(
                rule="TITLE",
                points=15,
                maximum=20,
                reason="Title similarity is 75%",
            ),
            ScoreItem(
                rule="PRODUCER",
                points=5,
                maximum=5,
                reason="Producer matches",
            ),
        )
    )

    assert result.total == 90.0
    assert result.maximum == 95.0
    assert result.confidence == pytest.approx(
        94.736842,
        rel=1e-6,
    )


def test_score_result_includes_match_in_total_and_maximum() -> None:
    result = ScoreResult(
        items=(
            ScoreItem(
                rule="MODEL_CODE",
                points=50,
                maximum=50,
                status=RuleStatus.MATCH,
                reason="Model code matches",
            ),
        )
    )

    assert result.total == 50.0
    assert result.maximum == 50.0
    assert result.confidence == 100.0


def test_score_result_includes_no_match_in_maximum_only() -> None:
    result = ScoreResult(
        items=(
            ScoreItem(
                rule="MODEL_CODE",
                points=0,
                maximum=50,
                status=RuleStatus.NO_MATCH,
                reason="Model code did not match",
            ),
        )
    )

    assert result.total == 0.0
    assert result.maximum == 50.0
    assert result.confidence == 0.0


def test_score_result_excludes_unknown_from_total_and_maximum() -> None:
    result = ScoreResult(
        items=(
            ScoreItem(
                rule="MODEL_CODE",
                points=0,
                maximum=50,
                status=RuleStatus.UNKNOWN,
                reason="Model code could not be determined",
            ),
        )
    )

    assert result.total == 0.0
    assert result.maximum == 0.0
    assert result.confidence == 0.0


def test_empty_score_result_has_zero_values() -> None:
    result = ScoreResult()

    assert result.items == ()
    assert result.total == 0.0
    assert result.maximum == 0.0
    assert result.confidence == 0.0
    assert result.is_empty is True


def test_score_result_converts_list_to_tuple() -> None:
    item = ScoreItem(
        rule="SERIES",
        points=20,
        maximum=20,
        reason="Series matches",
    )

    result = ScoreResult(items=[item])

    assert result.items == (item,)
    assert isinstance(result.items, tuple)


def test_score_result_from_items_accepts_generator() -> None:
    result = ScoreResult.from_items(
        ScoreItem(
            rule=f"RULE_{number}",
            points=1,
            maximum=1,
            reason=f"Rule {number} matched",
        )
        for number in range(3)
    )

    assert len(result.items) == 3
    assert result.total == 3.0
    assert result.maximum == 3.0
    assert result.confidence == 100.0


def test_score_result_returns_reasons_in_order() -> None:
    result = ScoreResult(
        items=(
            ScoreItem(
                rule="MODEL_CODE",
                points=50,
                maximum=50,
                reason="Model code matches",
            ),
            ScoreItem(
                rule="SERIES",
                points=0,
                maximum=20,
                reason="Series did not match",
            ),
        )
    )

    assert result.reasons == (
        "Model code matches",
        "Series did not match",
    )


def test_score_result_returns_matched_rules() -> None:
    result = ScoreResult(
        items=(
            ScoreItem(
                rule="MODEL_CODE",
                points=50,
                maximum=50,
                reason="Model code matches",
            ),
            ScoreItem(
                rule="SERIES",
                points=0,
                maximum=20,
                reason="Series did not match",
            ),
            ScoreItem(
                rule="TITLE",
                points=12,
                maximum=20,
                reason="Partial title match",
            ),
        )
    )

    assert result.matched_rules == (
        "MODEL_CODE",
        "TITLE",
    )


def test_score_result_returns_full_match_rules() -> None:
    result = ScoreResult(
        items=(
            ScoreItem(
                rule="MODEL_CODE",
                points=50,
                maximum=50,
                reason="Model code matches",
            ),
            ScoreItem(
                rule="TITLE",
                points=12,
                maximum=20,
                reason="Partial title match",
            ),
        )
    )

    assert result.full_match_rules == ("MODEL_CODE",)


def test_score_result_gets_item_case_insensitively() -> None:
    model_item = ScoreItem(
        rule="MODEL_CODE",
        points=50,
        maximum=50,
        reason="Model code matches",
    )

    result = ScoreResult(items=(model_item,))

    assert result.get_item("model_code") is model_item
    assert result.get_item(" MODEL_CODE ") is model_item


def test_score_result_returns_none_for_unknown_rule() -> None:
    result = ScoreResult(
        items=(
            ScoreItem(
                rule="MODEL_CODE",
                points=50,
                maximum=50,
                reason="Model code matches",
            ),
        )
    )

    assert result.get_item("SERIES") is None


def test_score_result_is_immutable() -> None:
    result = ScoreResult()

    with pytest.raises(AttributeError):
        result.confidence = 75.0