"""Model-based candidate selection for WooCommerce grill products.

This module combines grill-product filtering with extracted model identity
and controlled model fallback rules.

Exact model matches always have priority over fallback model matches.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from src.descriptions.matching.model_extractor import extract_model
from src.descriptions.matching.model_matcher import get_model_match_keys
from src.descriptions.matching.product_filter import is_grill_candidate


def select_model_candidates(
    source_model: str,
    products: Iterable[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Return grill products matching the best available model key.

    Products that are not valid grill candidates are ignored.

    Model keys are tried in priority order. As soon as one model key has
    matching grill products, those products are returned and lower-priority
    fallback keys are not considered.
    """
    grill_products = tuple(
        product
        for product in products
        if is_grill_candidate(product)
    )

    for model_key in get_model_match_keys(source_model):
        matches = tuple(
            product
            for product in grill_products
            if extract_model(
                str(product.get("name") or "")
            )
            == model_key
        )

        if matches:
            return matches

    return ()