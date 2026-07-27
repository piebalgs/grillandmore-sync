"""Decision engine for product matching."""

from __future__ import annotations

from src.descriptions.matching.models import (
    MatchResult,
    MatchStatus,
)

AUTO_THRESHOLD = 95.0
REVIEW_THRESHOLD = 80.0


def decide_match(result: MatchResult) -> MatchResult:
    """Assign a match status based on candidate confidence."""

    best = result.best_candidate

    if best is None:
        status = MatchStatus.UNMATCHED

    elif best.confidence >= AUTO_THRESHOLD:
        status = MatchStatus.AUTO

    elif best.confidence >= REVIEW_THRESHOLD:
        status = MatchStatus.REVIEW

    else:
        status = MatchStatus.UNMATCHED

    return MatchResult(
        description=result.description,
        candidates=result.candidates,
        status=status,
        note=result.note,
    )