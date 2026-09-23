"""Adapters for converting external product data into matching models.

This module contains only data conversion. It does not score candidates,
make matching decisions, or update WooCommerce.
"""

from __future__ import annotations

from typing import Any

from src.descriptions.matching.models import (
    DescriptionProduct,
    SupplierProduct,
)
from src.descriptions.parser import ProductDescription


def description_product_from_weber(
    product: ProductDescription,
) -> DescriptionProduct:
    """Convert one parsed Weber product into a matching description."""

    description_key = (
        product.import_id.strip()
        or product.sku.strip()
        or product.title.strip()
    )

    return DescriptionProduct(
        description_key=description_key,
        title=product.title,
        title_line_1=product.title_line_1,
        barbecue_code=product.sku,
        barcode="",
    )


def supplier_product_from_woocommerce(
    product: dict[str, Any],
) -> SupplierProduct:
    """Convert one WooCommerce product into a matching supplier product."""

    sku = str(product.get("sku") or "").strip()
    name = str(product.get("name") or "").strip()

    if not sku:
        raise ValueError("WooCommerce product must contain a SKU")

    if not name:
        raise ValueError("WooCommerce product must contain a name")

    return SupplierProduct(
        sku=sku,
        name=name,
        producer="Weber",
    )
