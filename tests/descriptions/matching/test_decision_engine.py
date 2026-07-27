"""Tests for match decision engine."""

from __future__ import annotations

from src.descriptions.matching.decision_engine import (
    AUTO_THRESHOLD,
    REVIEW_THRESHOLD,
    decide_match,
)
from src.descriptions.matching.models import (
    DescriptionProduct,
    MatchCandidate,
    MatchResult,
    MatchStatus,
    SupplierProduct,
)


def make_result(
    confidence: float | None,
    *,
    status: MatchStatus = MatchStatus.REVIEW,
    note: str = "",
) -> MatchResult:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )

    if confidence is None:
        candidates = ()
    else:
        supplier = SupplierProduct(
            sku="1500013",
            name="Weber Spirit EP-425",
        )
        candidates = (
            MatchCandidate(
                supplier=supplier,
                confidence=confidence,
                reasons=("Test candidate",),
            ),
        )

    return MatchResult(
        description=description,
        candidates=candidates,
        status=status,
        note=note,
    )


def test_threshold_constants() -> None:
    assert AUTO_THRESHOLD == 95.0
    assert REVIEW_THRESHOLD == 80.0


def test_decide_match_returns_unmatched_without_candidates() -> None:
    result = make_result(None)

    decided = decide_match(result)

    assert decided.status is MatchStatus.UNMATCHED
    assert decided.best_candidate is None


def test_decide_match_returns_auto_at_auto_threshold() -> None:
    result = make_result(95.0)

    decided = decide_match(result)

    assert decided.status is MatchStatus.AUTO


def test_decide_match_returns_auto_above_auto_threshold() -> None:
    result = make_result(100.0)

    decided = decide_match(result)

    assert decided.status is MatchStatus.AUTO


def test_decide_match_returns_review_at_review_threshold() -> None:
    result = make_result(80.0)

    decided = decide_match(result)

    assert decided.status is MatchStatus.REVIEW


def test_decide_match_returns_review_below_auto_threshold() -> None:
    result = make_result(94.99)

    decided = decide_match(result)

    assert decided.status is MatchStatus.REVIEW


def test_decide_match_returns_unmatched_below_review_threshold() -> None:
    result = make_result(79.99)

    decided = decide_match(result)

    assert decided.status is MatchStatus.UNMATCHED


def test_decide_match_returns_new_result() -> None:
    result = make_result(95.0)

    decided = decide_match(result)

    assert decided is not result


def test_decide_match_preserves_description() -> None:
    result = make_result(95.0)

    decided = decide_match(result)

    assert decided.description is result.description


def test_decide_match_preserves_candidates() -> None:
    result = make_result(95.0)

    decided = decide_match(result)

    assert decided.candidates is result.candidates


def test_decide_match_preserves_note() -> None:
    result = make_result(
        95.0,
        note="Manual review note",
    )

    decided = decide_match(result)

    assert decided.note == "Manual review note"


def test_decide_match_replaces_existing_status() -> None:
    result = make_result(
        79.99,
        status=MatchStatus.AUTO,
    )

    decided = decide_match(result)

    assert decided.status is MatchStatus.UNMATCHED