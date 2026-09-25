"""WooCommerce product filtering for grill matching.

This module decides whether a WooCommerce product may participate as a
Weber gas-grill matching candidate.

Filtering is based on structured WooCommerce category data rather than
product-name keywords.
"""

from __future__ import annotations

from typing import Any


WEBER_GAS_GRILL_CATEGORY_ID = 247
COVER_CATEGORY_ID = 458


def is_grill_candidate(product: dict[str, Any]) -> bool:
    """Return whether a WooCommerce product may be used as a grill candidate.

    A candidate must belong to the dedicated Weber gas-grill category.

    Products assigned to the WooCommerce cover category are excluded even
    when they also belong to the Weber gas-grill category.
    """
    categories = product.get("categories") or []

    category_ids = {
        category.get("id")
        for category in categories
    }

    return (
        WEBER_GAS_GRILL_CATEGORY_ID in category_ids
        and COVER_CATEGORY_ID not in category_ids
    )