"""Coordinator for explainable product-match scoring.

Individual scoring rules live in ``matching.rules``. This module executes
those rules and combines their results into one ``ScoreResult``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from src.descriptions.matching.models import (
    DescriptionProduct,
    SupplierProduct,
)
from src.descriptions.matching.rules import score_model_code
from src.descriptions.matching.score_models import (
    ScoreItem,
    ScoreResult,
)


ScoringRule = Callable[
    [DescriptionProduct, SupplierProduct],
    ScoreItem,
]


DEFAULT_RULES: tuple[ScoringRule, ...] = (
    score_model_code,
)


def calculate_score(
    description: DescriptionProduct,
    supplier: SupplierProduct,
    *,
    rules: Iterable[ScoringRule] | None = None,
) -> ScoreResult:
    """Calculate an explainable match score.

    Args:
        description:
            Weber shared-description record.

        supplier:
            Supplier product being evaluated.

        rules:
            Optional custom scoring-rule iterable. When omitted, the default
            matcher rules are used.

    Returns:
        Combined scoring result containing one item per executed rule.
    """
    selected_rules = (
        DEFAULT_RULES
        if rules is None
        else tuple(rules)
    )

    items = tuple(
        rule(description, supplier)
        for rule in selected_rules
    )

    return ScoreResult.from_items(items)
