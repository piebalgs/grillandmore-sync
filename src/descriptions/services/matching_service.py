"""Public service for description matching."""

from __future__ import annotations

from collections.abc import Iterable

from src.descriptions.matching.match_all import match_all
from src.descriptions.matching.models import (
    DescriptionProduct,
    MatchResult,
    SupplierProduct,
)
from src.descriptions.matching.scoring import ScoringRule


class MatchingService:
    """High-level service for matching description products."""

    def match(
        self,
        descriptions: Iterable[DescriptionProduct],
        suppliers: Iterable[SupplierProduct],
        *,
        rules: Iterable[ScoringRule] | None = None,
    ) -> tuple[MatchResult, ...]:
        """Match all descriptions against supplier products."""

        return match_all(
            descriptions,
            suppliers,
            rules=rules,
        )