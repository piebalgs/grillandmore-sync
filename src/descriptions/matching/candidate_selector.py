"""Candidate selection for description-to-supplier product matching.

This module evaluates supplier products against one description record,
converts scoring results into match candidates and returns the candidates
ordered from strongest to weakest.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.descriptions.matching.models import (
    DescriptionProduct,
    MatchCandidate,
    MatchResult,
    MatchStatus,
    SupplierProduct,
)
from src.descriptions.matching.scoring import (
    ScoringRule,
    calculate_score,
)


def select_candidates(
    description: DescriptionProduct,
    suppliers: Iterable[SupplierProduct],
    *,
    rules: Iterable[ScoringRule] | None = None,
) -> MatchResult:
    """Score and rank supplier-product candidates for one description.

    Args:
        description:
            Description record for which matching candidates are selected.

        suppliers:
            Supplier products to evaluate.

        rules:
            Optional custom scoring rules passed to ``calculate_score``.
            When omitted, the default scoring rules are used.

    Returns:
        Match result containing candidates ordered by confidence from highest
        to lowest.

        The initial status policy is intentionally conservative:

        - ``UNMATCHED`` when no supplier products are provided;
        - ``REVIEW`` when at least one candidate exists.

        Automatic acceptance thresholds are handled separately.
    """
    selected_rules = None if rules is None else tuple(rules)

    candidates = tuple(
        _build_candidate(
            description,
            supplier,
            rules=selected_rules,
        )
        for supplier in suppliers
    )

    ranked_candidates = tuple(
        sorted(
            candidates,
            key=lambda candidate: candidate.confidence,
            reverse=True,
        )
    )

    status = (
        MatchStatus.REVIEW
        if ranked_candidates
        else MatchStatus.UNMATCHED
    )

    return MatchResult(
        description=description,
        candidates=ranked_candidates,
        status=status,
    )


def _build_candidate(
    description: DescriptionProduct,
    supplier: SupplierProduct,
    *,
    rules: Iterable[ScoringRule] | None,
) -> MatchCandidate:
    """Create one match candidate from the calculated score."""
    score = calculate_score(
        description,
        supplier,
        rules=rules,
    )

    return MatchCandidate(
        supplier=supplier,
        confidence=score.confidence,
        reasons=score.reasons,
        match_type="SCORED",
    )