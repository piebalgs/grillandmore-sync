"""Model-code scoring rule for product matching.

This rule compares model identifiers found in the Weber description record
and the supplier product name. It does not make a final matching decision.
"""

from __future__ import annotations

from src.descriptions.matching.models import (
    DescriptionProduct,
    SupplierProduct,
)
from src.descriptions.matching.normalizer import (
    compact_match_text,
    normalize_product_name,
)
from src.descriptions.matching.score_models import (
    RuleStatus,
    ScoreItem,
)

RULE_NAME = "MODEL_CODE"
MAXIMUM_POINTS = 50.0


def _description_model_values(
    description: DescriptionProduct,
) -> tuple[str, ...]:
    """Return possible model-code values from a description record."""
    raw_values = (
        description.barbecue_code,
        description.description_key,
    )

    values: list[str] = []

    for value in raw_values:
        compact = compact_match_text(value)

        if compact and compact not in values:
            values.append(compact)

    return tuple(values)


def _supplier_comparison_values(
    supplier: SupplierProduct,
) -> tuple[str, ...]:
    """Return supplier-name forms used for model-code matching."""
    normalized = normalize_product_name(supplier.name)

    values = [
        normalized.compact,
        *normalized.unique_tokens,
    ]

    return tuple(
        dict.fromkeys(
            value
            for value in values
            if value
        )
    )


def score_model_code(
    description: DescriptionProduct,
    supplier: SupplierProduct,
) -> ScoreItem:
    """Score model-code correspondence between two product records.

    An exact compact model-code occurrence receives all available points.

    Examples considered equivalent:

    - ``EP-425`` and ``EP425``
    - ``SPIRIT_EP_425`` and ``Spirit EP-425``
    - ``GENESIS_E_335`` and ``Genesis E-335``

    Args:
        description:
            Weber shared-description record.

        supplier:
            Supplier product being evaluated.

    Returns:
        Explainable scoring item for the model-code rule.
    """
    description_values = _description_model_values(description)
    supplier_values = _supplier_comparison_values(supplier)

    if not description_values:
        return ScoreItem(
            rule=RULE_NAME,
            points=0,
            maximum=MAXIMUM_POINTS,
            status=RuleStatus.UNKNOWN,
            reason="Description does not contain a model code",
        )

    if not supplier_values:
        return ScoreItem(
            rule=RULE_NAME,
            points=0,
            maximum=MAXIMUM_POINTS,
            status=RuleStatus.UNKNOWN,
            reason="Supplier product does not contain comparison text",
        )

    supplier_compact = supplier_values[0]

    for model_code in description_values:
        if model_code == supplier_compact:
            return ScoreItem(
                rule=RULE_NAME,
                points=MAXIMUM_POINTS,
                maximum=MAXIMUM_POINTS,
                status=RuleStatus.MATCH,
                reason="Model code matches the complete supplier product name",
            )

        if model_code in supplier_compact:
            return ScoreItem(
                rule=RULE_NAME,
                points=MAXIMUM_POINTS,
                maximum=MAXIMUM_POINTS,
                status=RuleStatus.MATCH,
                reason=f"Model code matches: {model_code}",
            )

    return ScoreItem(
        rule=RULE_NAME,
        points=0,
        maximum=MAXIMUM_POINTS,
        status=RuleStatus.NO_MATCH,
        reason="Model code did not match",
    )