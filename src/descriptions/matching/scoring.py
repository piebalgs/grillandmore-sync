"""Coordinator for explainable product-match scoring.

Individual scoring rules live in ``matching.rules``. This module executes
those rules and combines their results into one ``ScoreResult``.

EAN is intentionally available as an opt-in rule in the first EAN phase.
It will join ``DEFAULT_RULES`` only after Weber EAN values are populated
reliably by the description-data mapper.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from src.descriptions.matching.models import (
    DescriptionProduct,
    SupplierProduct,
)
from src.descriptions.matching.rules import (
    score_model_code,
    score_producer,
    score_series,
    score_title_similarity,
)
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
    score_series,
    score_producer,
    score_title_similarity,
)


def calculate_score(
    description: DescriptionProduct,
    supplier: SupplierProduct,
    *,
    rules: Iterable[ScoringRule] | None = None,
) -> ScoreResult:
    """Calculate an explainable match score.

    Pass ``rules=(score_ean, *DEFAULT_RULES)`` when EAN evaluation is
    explicitly required.
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
