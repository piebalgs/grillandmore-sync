"""Apply one generated product description to multiple WooCommerce targets.

This module coordinates target-SKU mapping with the existing ProductUpdater.

It does not perform matching, translation, formatting, quality checking,
or direct WooCommerce API operations.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.descriptions.models import (
    FormattedProduct,
    QualityReport,
)
from src.descriptions.target_mapper import map_to_target
from src.descriptions.updater import (
    ProductUpdater,
    UpdateResult,
)


def update_targets(
    *,
    product: FormattedProduct,
    quality_report: QualityReport,
    target_skus: Iterable[str],
    updater: ProductUpdater,
) -> tuple[UpdateResult, ...]:
    """Apply one generated description to multiple WooCommerce target SKUs.

    Each target receives its own target-specific FormattedProduct and
    QualityReport. The supplied ProductUpdater controls whether the
    operation is a dry run or a real WooCommerce update.
    """
    if not isinstance(product, FormattedProduct):
        raise TypeError(
            "product jābūt FormattedProduct objektam."
        )

    if not isinstance(quality_report, QualityReport):
        raise TypeError(
            "quality_report jābūt QualityReport objektam."
        )

    if not isinstance(updater, ProductUpdater):
        raise TypeError(
            "updater jābūt ProductUpdater objektam."
        )
    if isinstance(target_skus, str):
        raise TypeError(
            "target_skus jābūt SKU kolekcijai, nevis teksta virknei."
        )
    target_skus = tuple(target_skus)

    if not target_skus:
        raise ValueError(
            "target_skus nedrīkst būt tukšs."
        )

    results: list[UpdateResult] = []

    for target_sku in target_skus:
        mapped_product, mapped_quality = map_to_target(
            product=product,
            quality_report=quality_report,
            target_sku=target_sku,
        )

        result = updater.update(
            product=mapped_product,
            quality_report=mapped_quality,
        )

        results.append(result)

    return tuple(results)