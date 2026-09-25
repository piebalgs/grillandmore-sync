"""Map generated product content to a WooCommerce target SKU.

This module does not perform matching, translation, quality checking,
or WooCommerce updates.

It only creates target-specific immutable copies of already generated
and quality-checked product content.
"""

from __future__ import annotations

from dataclasses import replace

from src.descriptions.models import (
    FormattedProduct,
    QualityReport,
)


def map_to_target(
    *,
    product: FormattedProduct,
    quality_report: QualityReport,
    target_sku: str,
) -> tuple[FormattedProduct, QualityReport]:
    """Map generated content to one WooCommerce target SKU.

    The generated description content and quality result are preserved.
    Only the SKU identity is replaced with the actual WooCommerce target
    SKU.

    The source objects are immutable and remain unchanged.
    """
    if not isinstance(product, FormattedProduct):
        raise TypeError(
            "product jābūt FormattedProduct objektam."
        )

    if not isinstance(quality_report, QualityReport):
        raise TypeError(
            "quality_report jābūt QualityReport objektam."
        )

    if product.sku.strip() != quality_report.sku.strip():
        raise ValueError(
            "FormattedProduct un QualityReport avota SKU nesakrīt."
        )

    if not isinstance(target_sku, str):
        raise TypeError(
            "target_sku jābūt teksta vērtībai."
        )

    normalized_target_sku = target_sku.strip()

    if not normalized_target_sku:
        raise ValueError(
            "target_sku nedrīkst būt tukšs."
        )

    mapped_product = replace(
        product,
        sku=normalized_target_sku,
    )

    mapped_quality = replace(
        quality_report,
        sku=normalized_target_sku,
    )

    return mapped_product, mapped_quality