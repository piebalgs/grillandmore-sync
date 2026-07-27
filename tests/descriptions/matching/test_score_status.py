"""Tests for semantic scoring statuses."""

import pytest

from src.descriptions.matching.score_models import (
    RuleStatus,
    ScoreItem,
    ScoreResult,
)


def item(rule, points, maximum, status=None):
    return ScoreItem(
        rule=rule,
        points=points,
        maximum=maximum,
        reason=f"{rule} result",
        status=status,
    )


def test_existing_rules_infer_match_from_positive_points():
    result = item("MODEL", 50, 50)
    assert result.status is RuleStatus.MATCH


def test_existing_rules_infer_no_match_from_zero_points():
    result = item("MODEL", 0, 50)
    assert result.status is RuleStatus.NO_MATCH


def test_unknown_rule_is_excluded_from_available_maximum():
    result = ScoreResult(
        items=(
            item("EAN", 0, 100, RuleStatus.UNKNOWN),
            item("MODEL", 50, 50, RuleStatus.MATCH),
        )
    )

    assert result.total == 50
    assert result.maximum == 50
    assert result.confidence == 100
    assert result.unknown_rules == ("EAN",)


def test_conflict_remains_part_of_available_maximum():
    result = ScoreResult(
        items=(
            item("EAN", 0, 100, RuleStatus.CONFLICT),
            item("MODEL", 50, 50, RuleStatus.MATCH),
        )
    )

    assert result.total == 50
    assert result.maximum == 150
    assert result.confidence == pytest.approx(33.3333333333)
    assert result.conflict_rules == ("EAN",)
