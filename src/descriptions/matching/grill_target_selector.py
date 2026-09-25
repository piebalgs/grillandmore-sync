"""Select WooCommerce grill targets for one Weber product description.

This module connects parsed Weber product data with the existing
model-extraction and model-candidate-selection logic.

It does not translate descriptions, score generic matches, or update
WooCommerce.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from src.descriptions.matching.model_candidate_selector import (
    select_model_candidates,
)
from src.descriptions.matching.model_extractor import (
    extract_model_from_texts,
)
from src.descriptions.parser import ProductDescription


def select_grill_targets(
    *,
    product: ProductDescription,
    woo_products: Iterable[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Return WooCommerce grill products matching one Weber product.

    Model identity is extracted from the Weber title fields first.
    The source description may refine a Q-series model when it contains
    a more precise variant such as Q2800N+ or Q3200N+.

    Zero, one, or multiple WooCommerce targets may be returned.
    """
    if not isinstance(product, ProductDescription):
        raise TypeError(
            "product jābūt ProductDescription objektam."
        )

    source_model = extract_model_from_texts(
        product.title,
        product.title_line_1,
        product.source_description,
    )

    if not source_model:
        return ()

    return select_model_candidates(
        source_model,
        woo_products,
    )