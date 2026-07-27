"""EAN/GTIN matching expert."""

from __future__ import annotations

import re

from src.descriptions.matching.models import (
    DescriptionProduct,
    SupplierProduct,
)
from src.descriptions.matching.score_models import (
    RuleStatus,
    ScoreItem,
)

MAXIMUM_POINTS = 100.0


def normalize_barcode(value: str | None) -> str:
    """Return digits-only EAN/GTIN representation.

    Spreadsheet exports sometimes turn barcodes into values such as
    ``77924920172.0``. A trailing decimal zero is removed before all
    non-digit separators are stripped.
    """

    text = str(value or "").strip()

    if not text:
        return ""

    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", maxsplit=1)[0]

    return "".join(character for character in text if character.isdigit())


def score_ean(
    description: DescriptionProduct,
    supplier: SupplierProduct,
) -> ScoreItem:
    """Compare Weber and supplier EAN/GTIN values."""

    description_ean = normalize_barcode(description.barcode)
    supplier_ean = normalize_barcode(supplier.barcode)

    if not description_ean or not supplier_ean:
        missing = []

        if not description_ean:
            missing.append("Weber EAN")
        if not supplier_ean:
            missing.append("supplier EAN")

        return ScoreItem(
            rule="EAN",
            points=0,
            maximum=MAXIMUM_POINTS,
            status=RuleStatus.UNKNOWN,
            reason="EAN unavailable: " + " and ".join(missing),
        )

    if description_ean == supplier_ean:
        return ScoreItem(
            rule="EAN",
            points=MAXIMUM_POINTS,
            maximum=MAXIMUM_POINTS,
            status=RuleStatus.MATCH,
            reason=f"EAN identical: {description_ean}",
        )

    return ScoreItem(
        rule="EAN",
        points=0,
        maximum=MAXIMUM_POINTS,
        status=RuleStatus.CONFLICT,
        reason=(
            "EAN conflict: "
            f"Weber {description_ean}, supplier {supplier_ean}"
        ),
    )
