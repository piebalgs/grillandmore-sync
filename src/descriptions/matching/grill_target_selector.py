
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


def _source_requires_stand(
    product: ProductDescription,
) -> bool:
    """Return whether the source explicitly identifies a stand variant."""

    source_text = " ".join(
        text
        for text in (
            product.title,
            product.title_line_1,
        )
        if text
    ).lower()

    return (
        "w/stand" in source_text
        or "with stand" in source_text
    )


def _woo_product_has_stand(
    product: dict[str, Any],
) -> bool:
    """Return whether a WooCommerce name identifies a stand variant."""

    name = str(product.get("name") or "").lower()

    return (
        "ar statīvu" in name
        or "ar stativu" in name
        or "w/stand" in name
        or "with stand" in name
    )


def select_grill_targets(
    *,
    product: ProductDescription,
    woo_products: Iterable[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Return WooCommerce grill products matching one Weber product.

    Stand variants are matched explicitly.

    For the plain Q1200N source, stand variants are excluded to
    prevent assigning the wrong description to the stand model.

    Other grill models retain their existing candidate-selection
    behavior.
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

    candidates = select_model_candidates(
        source_model,
        woo_products,
    )

    if _source_requires_stand(product):
        return tuple(
            candidate
            for candidate in candidates
            if _woo_product_has_stand(candidate)
        )

    if source_model == "Q1200N":
        return tuple(
            candidate
            for candidate in candidates
            if not _woo_product_has_stand(candidate)
        )

    return candidates
