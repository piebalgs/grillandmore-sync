"""Batch matching for product descriptions.

This module applies the high-level matcher to multiple description records
using the same supplier-product collection.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.descriptions.matching.matcher import match_description
from src.descriptions.matching.models import (
    DescriptionProduct,
    MatchResult,
    SupplierProduct,
)
from src.descriptions.matching.scoring import ScoringRule


def match_all(
    descriptions: Iterable[DescriptionProduct],
    suppliers: Iterable[SupplierProduct],
    *,
    rules: Iterable[ScoringRule] | None = None,
) -> tuple[MatchResult, ...]:
    """Match all descriptions against the supplied products.

    Supplier products and optional scoring rules are materialized once so that
    generators can be reused safely for every description record.

    Args:
        descriptions:
            Description records to match.

        suppliers:
            Supplier products evaluated for every description.

        rules:
            Optional custom scoring rules. When omitted, the default scoring
            rules are used.

    Returns:
        Match results in the same order as the input descriptions.
    """
    reusable_suppliers = tuple(suppliers)
    reusable_rules = None if rules is None else tuple(rules)

    return tuple(
        match_description(
            description,
            reusable_suppliers,
            rules=reusable_rules,
        )
        for description in descriptions
    )