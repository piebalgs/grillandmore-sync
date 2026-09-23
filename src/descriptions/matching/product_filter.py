"""WooCommerce product filtering for grill matching.

This module decides whether a WooCommerce product may participate as a
grill-matching candidate.

Filtering is based on structured WooCommerce category data rather than
product-name keywords.
"""

from __future__ import annotations

from typing import Any


COVER_CATEGORY_ID = 458


def is_grill_candidate(product: dict[str, Any]) -> bool:
    """Return whether a WooCommerce product may be used as a grill candidate.

    Products assigned to the WooCommerce cover category are excluded from
    grill matching even when they also belong to a grill category.
    """
    categories = product.get("categories") or []

    return not any(
        category.get("id") == COVER_CATEGORY_ID
        for category in categories
    )