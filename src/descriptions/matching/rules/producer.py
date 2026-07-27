"""Producer scoring rule for product matching.

Description records handled by this matcher originate from the Weber CSV.
Therefore their expected producer is Weber. The supplier-side producer is
read from the supplier XML product record.
"""

from __future__ import annotations

from src.descriptions.matching.constants import PRODUCER_POINTS
from src.descriptions.matching.models import (
    DescriptionProduct,
    SupplierProduct,
)
from src.descriptions.matching.normalizer import (
    compact_match_text,
    unique_match_tokens,
)
from src.descriptions.matching.score_models import (
    RuleStatus,
    ScoreItem,
)


RULE_NAME = "PRODUCER"
EXPECTED_PRODUCER = "WEBER"


def _normalize_producer(value: str | None) -> str:
    """Return a compact normalized producer value."""
    if not value:
        return ""

    return compact_match_text(value)


def _producer_tokens(value: str | None) -> tuple[str, ...]:
    """Return unique normalized tokens from a producer value."""
    if not value:
        return ()

    return unique_match_tokens(value)


def _is_expected_producer(value: str | None) -> bool:
    """Return whether a supplier producer represents Weber."""
    normalized_expected = _normalize_producer(EXPECTED_PRODUCER)
    normalized_value = _normalize_producer(value)

    if not normalized_value:
        return False

    if normalized_value == normalized_expected:
        return True

    return normalized_expected in _producer_tokens(value)


def score_producer(
    description: DescriptionProduct,
    supplier: SupplierProduct,
) -> ScoreItem:
    """Score the supplier producer against the expected Weber producer.

    The description argument is accepted to follow the common scoring-rule
    interface. Its contents are not used because every description record
    processed by this matcher originates from the Weber CSV.
    """
    del description

    if not supplier.producer:
        return ScoreItem(
            rule=RULE_NAME,
            points=0,
            maximum=PRODUCER_POINTS,
            status=RuleStatus.NO_MATCH,
            reason="Supplier producer could not be determined",
        )

    if _is_expected_producer(supplier.producer):
        return ScoreItem(
            rule=RULE_NAME,
            points=PRODUCER_POINTS,
            maximum=PRODUCER_POINTS,
            status=RuleStatus.MATCH,
            reason=f"Producer matches: {EXPECTED_PRODUCER}",
        )

    return ScoreItem(
        rule=RULE_NAME,
        points=0,
        maximum=PRODUCER_POINTS,
        status=RuleStatus.NO_MATCH,
        reason=(
            f"Producer mismatch: "
            f"{EXPECTED_PRODUCER} vs {supplier.producer}"
        ),
    )