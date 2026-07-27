"""High-level product-description matching service.

This module combines candidate selection and decision making into one public
function for matching a single description against supplier products.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.descriptions.matching.candidate_selector import (
    select_candidates,
)
from src.descriptions.matching.decision_engine import (
    decide_match,
)
from src.descriptions.matching.models import (
    DescriptionProduct,
    MatchResult,
    SupplierProduct,
)
from src.descriptions.matching.scoring import ScoringRule


def match_description(
    description: DescriptionProduct,
    suppliers: Iterable[SupplierProduct],
    *,
    rules: Iterable[ScoringRule] | None = None,
) -> MatchResult:
    """Match one description record against supplier products.

    The matching pipeline consists of two steps:

    1. score and rank supplier-product candidates;
    2. assign the final match status from the strongest candidate.

    Args:
        description:
            Description record to match.

        suppliers:
            Supplier products to evaluate.

        rules:
            Optional custom scoring rules. When omitted, the default scoring
            rules are used.

    Returns:
        Final match result containing ranked candidates and the decided status.
    """
    selected = select_candidates(
        description,
        suppliers,
        rules=rules,
    )

    return decide_match(selected)