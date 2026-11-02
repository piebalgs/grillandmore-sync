
"""SKU-specific configuration for generated product descriptions.

This module does not access or modify WooCommerce.
"""

from dataclasses import replace
from html import escape
from typing import Mapping

from src.descriptions.models import FormattedProduct


# Only confirmed product configurations belong here.
TARGET_CONFIGURATION: Mapping[str, str] = {
    "1501086": "Komplektā ietilpst Weber Q1200N gāzes grils un statīvs.",
}


def apply_target_configuration(
    *,
    product: FormattedProduct,
    target_sku: str,
) -> FormattedProduct:
    """Return a new product with optional SKU-specific configuration."""

    if not isinstance(product, FormattedProduct):
        raise TypeError("product jābūt FormattedProduct objektam.")

    if not isinstance(target_sku, str):
        raise TypeError("target_sku jābūt teksta vērtībai.")

    normalized_sku = target_sku.strip()

    if not normalized_sku:
        raise ValueError("target_sku nedrīkst būt tukšs.")

    if product.sku.strip() != normalized_sku:
        raise ValueError("Produkta SKU nesakrīt ar target_sku.")

    configuration = TARGET_CONFIGURATION.get(normalized_sku)

    if not configuration:
        return product

    section = (
        "\n\n<h2>Komplektācija</h2>\n"
        f"<p>{escape(configuration)}</p>"
    )

    # Avoid adding the same section twice.
    if "<h2>Komplektācija</h2>" in product.description_html:
        raise ValueError(
            "Aprakstā jau ir komplektācijas sadaļa."
        )

    return replace(
        product,
        description_html=product.description_html.rstrip() + section,
    )
