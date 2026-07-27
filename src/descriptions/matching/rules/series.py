"""Series scoring rule for product matching."""

from __future__ import annotations

from src.descriptions.matching.constants import SERIES_POINTS
from src.descriptions.matching.data.series import SERIES_NAMES
from src.descriptions.matching.models import (
    DescriptionProduct,
    SupplierProduct,
)
from src.descriptions.matching.normalizer import compact_match_text
from src.descriptions.matching.score_models import (
    RuleStatus,
    ScoreItem,
)


RULE_NAME = "SERIES"


def find_series(text: str | None) -> str | None:
    """Return a known Weber series found in the supplied text."""
    if not text:
        return None

    normalized_text = compact_match_text(text)

    if not normalized_text:
        return None

    candidates = sorted(
        SERIES_NAMES,
        key=lambda series: len(compact_match_text(series)),
        reverse=True,
    )

    for series in candidates:
        normalized_series = compact_match_text(series)

        if normalized_series and normalized_series in normalized_text:
            return series

    return None


def score_series(
    description: DescriptionProduct,
    supplier: SupplierProduct,
) -> ScoreItem:
    """Score whether two product records belong to the same Weber series."""
    description_series = (
        find_series(description.barbecue_code)
        or find_series(description.description_key)
    )
    supplier_series = find_series(supplier.name)

    if description_series is None and supplier_series is None:
        return ScoreItem(
            rule=RULE_NAME,
            points=0,
            maximum=SERIES_POINTS,
            status=RuleStatus.UNKNOWN,
            reason="Series could not be determined for either product",
        )

    if description_series is None:
        return ScoreItem(
            rule=RULE_NAME,
            points=0,
            maximum=SERIES_POINTS,
            status=RuleStatus.UNKNOWN,
            reason="Description series could not be determined",
        )

    if supplier_series is None:
        return ScoreItem(
            rule=RULE_NAME,
            points=0,
            maximum=SERIES_POINTS,
            status=RuleStatus.UNKNOWN,
            reason="Supplier series could not be determined",
        )

    if description_series == supplier_series:
        return ScoreItem(
            rule=RULE_NAME,
            points=SERIES_POINTS,
            maximum=SERIES_POINTS,
            status=RuleStatus.MATCH,
            reason=f"Series matches: {description_series}",
        )

    return ScoreItem(
        rule=RULE_NAME,
        points=0,
        maximum=SERIES_POINTS,
        status=RuleStatus.NO_MATCH,
        reason=(
            f"Series mismatch: "
            f"{description_series} vs {supplier_series}"
        ),
    )