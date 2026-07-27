"""First complete orchestration layer for product matching.

This module connects the existing matching components:

1. score every supplier product against one Weber description;
2. discard candidates below the configured minimum confidence;
3. sort candidates from strongest to weakest;
4. keep only the requested number of candidates;
5. ask the decision engine for the final AUTO / REVIEW / UNMATCHED status.

The module intentionally contains no product-specific comparison rules.
Those remain in ``scoring.py`` and ``matching.rules``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.descriptions.matching.decision_engine import decide_match
from src.descriptions.matching.models import (
    DescriptionProduct,
    MatchCandidate,
    MatchResult,
    SupplierProduct,
)
from src.descriptions.matching.scoring import (
    ScoringRule,
    calculate_score,
)


@dataclass(frozen=True, slots=True)
class MatchingEngineConfig:
    """Configuration for the matching orchestration layer.

    Attributes:
        candidate_limit:
            Maximum number of ranked candidates retained in the result.

        minimum_confidence:
            Candidates below this confidence are discarded. The decision
            engine still decides whether retained candidates qualify for
            AUTO or REVIEW.
    """

    candidate_limit: int = 5
    minimum_confidence: float = 0.0

    def __post_init__(self) -> None:
        candidate_limit = int(self.candidate_limit)
        minimum_confidence = float(self.minimum_confidence)

        if candidate_limit <= 0:
            raise ValueError("candidate_limit must be greater than 0")

        if not 0.0 <= minimum_confidence <= 100.0:
            raise ValueError(
                "minimum_confidence must be between 0 and 100"
            )

        object.__setattr__(self, "candidate_limit", candidate_limit)
        object.__setattr__(
            self,
            "minimum_confidence",
            minimum_confidence,
        )


class MatchingEngine:
    """Match Weber description records to supplier products."""

    def __init__(
        self,
        *,
        config: MatchingEngineConfig | None = None,
        rules: Iterable[ScoringRule] | None = None,
    ) -> None:
        self.config = config or MatchingEngineConfig()
        self.rules = None if rules is None else tuple(rules)

    def score_candidate(
        self,
        description: DescriptionProduct,
        supplier: SupplierProduct,
    ) -> MatchCandidate:
        """Score one description/supplier pair."""

        score = calculate_score(
            description,
            supplier,
            rules=self.rules,
        )

        return MatchCandidate(
            supplier=supplier,
            confidence=score.confidence,
            reasons=score.reasons,
            match_type="SCORED",
        )

    def rank_candidates(
        self,
        description: DescriptionProduct,
        suppliers: Iterable[SupplierProduct],
    ) -> tuple[MatchCandidate, ...]:
        """Score, filter and rank supplier candidates.

        Sorting is deterministic. Candidates with equal confidence are
        ordered by supplier SKU and then normalized product name.
        """

        candidates = (
            self.score_candidate(description, supplier)
            for supplier in suppliers
        )

        retained = (
            candidate
            for candidate in candidates
            if candidate.confidence >= self.config.minimum_confidence
        )

        ranked = sorted(
            retained,
            key=lambda candidate: (
                -candidate.confidence,
                candidate.supplier.sku.casefold(),
                candidate.supplier.normalized_name,
            ),
        )

        return tuple(ranked[: self.config.candidate_limit])

    def match_one(
        self,
        description: DescriptionProduct,
        suppliers: Iterable[SupplierProduct],
    ) -> MatchResult:
        """Match one Weber description to a supplier-product collection."""

        candidates = self.rank_candidates(
            description,
            suppliers,
        )

        undecided = MatchResult(
            description=description,
            candidates=candidates,
        )

        return decide_match(undecided)

    def match_all(
        self,
        descriptions: Iterable[DescriptionProduct],
        suppliers: Iterable[SupplierProduct],
    ) -> tuple[MatchResult, ...]:
        """Match every description against the same supplier collection.

        Supplier iterables are materialized once so generators are safe to
        reuse for every description.
        """

        supplier_pool = tuple(suppliers)

        return tuple(
            self.match_one(description, supplier_pool)
            for description in descriptions
        )


def match_description(
    description: DescriptionProduct,
    suppliers: Iterable[SupplierProduct],
    *,
    config: MatchingEngineConfig | None = None,
    rules: Iterable[ScoringRule] | None = None,
) -> MatchResult:
    """Convenience function for matching one description."""

    engine = MatchingEngine(
        config=config,
        rules=rules,
    )

    return engine.match_one(description, suppliers)


def match_descriptions(
    descriptions: Iterable[DescriptionProduct],
    suppliers: Iterable[SupplierProduct],
    *,
    config: MatchingEngineConfig | None = None,
    rules: Iterable[ScoringRule] | None = None,
) -> tuple[MatchResult, ...]:
    """Convenience function for matching multiple descriptions."""

    engine = MatchingEngine(
        config=config,
        rules=rules,
    )

    return engine.match_all(descriptions, suppliers)
