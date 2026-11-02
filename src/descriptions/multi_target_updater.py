
"""Apply one generated product description to multiple WooCommerce targets.

This module coordinates target-SKU mapping with the existing ProductUpdater.

It does not perform matching, translation, formatting, quality checking,
or direct WooCommerce API operations.

SKU-specific configuration sections are applied and their HTML structure
is validated before the product is passed to ProductUpdater.
"""

from __future__ import annotations

from collections.abc import Iterable
from html.parser import HTMLParser

from src.descriptions.models import (
    FormattedProduct,
    QualityReport,
)
from src.descriptions.target_configuration import (
    apply_target_configuration,
)
from src.descriptions.target_mapper import map_to_target
from src.descriptions.updater import (
    ProductUpdater,
    UpdateResult,
)


class _ConfigurationHTMLValidator(HTMLParser):
    """Validate basic HTML structure of a configured description."""

    ALLOWED_TAGS = {
        "p",
        "h2",
        "h3",
        "strong",
        "em",
        "ul",
        "ol",
        "li",
        "br",
        "table",
        "tbody",
        "tr",
        "th",
        "td",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag not in self.ALLOWED_TAGS:
            raise ValueError(
                f"Neatļauts HTML tags: {tag}"
            )

        allowed_attrs = {
            "table": [("class", "product-specifications")],
            "th": [("scope", "row")],
        }

        if attrs and attrs != allowed_attrs.get(tag, []):
            raise ValueError(
                "HTML atribūti nav atļauti."
            )

        if tag != "br":
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        if tag != "br" or attrs:
            raise ValueError(
                f"Nederīgs pašnoslēdzošs HTML tags: {tag}"
            )

    def handle_endtag(self, tag: str) -> None:
        if tag not in self.ALLOWED_TAGS or tag == "br":
            raise ValueError(
                f"Nederīgs HTML beigu tags: {tag}"
            )

        if not self.stack or self.stack[-1] != tag:
            raise ValueError(
                "Nepareiza HTML tagu secība."
            )

        self.stack.pop()


def _validate_configuration_html(html: str) -> None:
    """Reject invalid HTML structure in a configured description."""

    if not isinstance(html, str):
        raise TypeError(
            "HTML aprakstam jābūt teksta vērtībai."
        )

    validator = _ConfigurationHTMLValidator()
    validator.feed(html)
    validator.close()

    if validator.stack:
        raise ValueError(
            "HTML satur neaizvērtus tagus."
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

        configured_product = apply_target_configuration(
            product=mapped_product,
            target_sku=target_sku,
        )

        if configured_product is not mapped_product:
            _validate_configuration_html(
                configured_product.description_html
            )

        result = updater.update(
            product=configured_product,
            quality_report=mapped_quality,
        )

        results.append(result)

    return tuple(results)
