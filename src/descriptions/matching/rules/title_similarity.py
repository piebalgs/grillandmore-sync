"""Title-similarity scoring rule for product matching.

The rule compares the normalized description title with the normalized
supplier-product name using RapidFuzz.

Low similarity values are ignored to prevent unrelated product names from
receiving misleading partial points.
"""

from __future__ import annotations

from rapidfuzz import fuzz

from src.descriptions.matching.models import (
    DescriptionProduct,
    SupplierProduct,
)
from src.descriptions.matching.score_models import ScoreItem


RULE_NAME = "TITLE_SIMILARITY"
MAXIMUM_POINTS = 25.0
MINIMUM_SIMILARITY = 60.0


def calculate_title_similarity(
    description: DescriptionProduct,
    supplier: SupplierProduct,
) -> float:
    """Return normalized title similarity from 0.0 to 100.0."""

    description_name = description.normalized_name
    supplier_name = supplier.normalized_name

    if not description_name or not supplier_name:
        return 0.0

    return float(
        fuzz.WRatio(
            description_name,
            supplier_name,
            processor=None,
        )
    )


def similarity_to_points(similarity: float) -> float:
    """Convert title similarity into matcher points.

    Similarities below ``MINIMUM_SIMILARITY`` receive no points. Accepted
    similarities are converted proportionally to ``MAXIMUM_POINTS``.
    """

    normalized_similarity = min(
        100.0,
        max(0.0, float(similarity)),
    )

    if normalized_similarity < MINIMUM_SIMILARITY:
        return 0.0

    return round(
        MAXIMUM_POINTS * normalized_similarity / 100.0,
        2,
    )


def score_title_similarity(
    description: DescriptionProduct,
    supplier: SupplierProduct,
) -> ScoreItem:
    """Score similarity between description and supplier product titles."""

    similarity = calculate_title_similarity(
        description,
        supplier,
    )
    points = similarity_to_points(similarity)

    if points == 0.0:
        reason = (
            "Title similarity is below the minimum threshold: "
            f"{similarity:.1f}%"
        )
    else:
        reason = f"Title similarity: {similarity:.1f}%"

    return ScoreItem(
        rule=RULE_NAME,
        points=points,
        maximum=MAXIMUM_POINTS,
        reason=reason,
    )