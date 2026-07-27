"""Tests for supplier-product candidate selection."""

from __future__ import annotations

from src.descriptions.matching.candidate_selector import (
    select_candidates,
)
from src.descriptions.matching.models import (
    DescriptionProduct,
    MatchStatus,
    SupplierProduct,
)
from src.descriptions.matching.score_models import ScoreItem


def test_select_candidates_returns_match_result_for_description() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )

    result = select_candidates(
        description,
        [],
    )

    assert result.description is description


def test_select_candidates_returns_unmatched_for_empty_suppliers() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )

    result = select_candidates(
        description,
        [],
    )

    assert result.candidates == ()
    assert result.best_candidate is None
    assert result.status is MatchStatus.UNMATCHED


def test_select_candidates_returns_review_when_candidate_exists() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    result = select_candidates(
        description,
        [supplier],
    )

    assert result.status is MatchStatus.REVIEW
    assert len(result.candidates) == 1


def test_select_candidates_preserves_supplier_product() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    result = select_candidates(
        description,
        [supplier],
    )

    assert result.candidates[0].supplier is supplier


def test_select_candidates_uses_score_confidence() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    def custom_rule(
        description: DescriptionProduct,
        supplier: SupplierProduct,
    ) -> ScoreItem:
        return ScoreItem(
            rule="CUSTOM",
            points=8.0,
            maximum=10.0,
            reason="Custom score",
        )

    result = select_candidates(
        description,
        [supplier],
        rules=[custom_rule],
    )

    assert result.candidates[0].confidence == 80.0


def test_select_candidates_copies_score_reasons() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    def first_rule(
        description: DescriptionProduct,
        supplier: SupplierProduct,
    ) -> ScoreItem:
        return ScoreItem(
            rule="FIRST",
            points=5.0,
            maximum=10.0,
            reason="First reason",
        )

    def second_rule(
        description: DescriptionProduct,
        supplier: SupplierProduct,
    ) -> ScoreItem:
        return ScoreItem(
            rule="SECOND",
            points=10.0,
            maximum=10.0,
            reason="Second reason",
        )

    result = select_candidates(
        description,
        [supplier],
        rules=[first_rule, second_rule],
    )

    assert result.candidates[0].reasons == (
        "First reason",
        "Second reason",
    )


def test_select_candidates_sets_scored_match_type() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    result = select_candidates(
        description,
        [supplier],
    )

    assert result.candidates[0].match_type == "SCORED"


def test_select_candidates_orders_candidates_by_confidence() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    weak_supplier = SupplierProduct(
        sku="WEAK",
        name="Completely different product",
    )
    strong_supplier = SupplierProduct(
        sku="STRONG",
        name="Weber Spirit EP-425",
    )

    def sku_rule(
        description: DescriptionProduct,
        supplier: SupplierProduct,
    ) -> ScoreItem:
        points = 9.0 if supplier.sku == "STRONG" else 2.0

        return ScoreItem(
            rule="SKU_TEST",
            points=points,
            maximum=10.0,
            reason=f"Score for {supplier.sku}",
        )

    result = select_candidates(
        description,
        [weak_supplier, strong_supplier],
        rules=[sku_rule],
    )

    assert tuple(
        candidate.supplier.sku
        for candidate in result.candidates
    ) == (
        "STRONG",
        "WEAK",
    )

    assert tuple(
        candidate.confidence
        for candidate in result.candidates
    ) == (
        90.0,
        20.0,
    )


def test_best_candidate_returns_highest_ranked_candidate() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    first_supplier = SupplierProduct(
        sku="LOW",
        name="Low candidate",
    )
    second_supplier = SupplierProduct(
        sku="HIGH",
        name="High candidate",
    )

    def sku_rule(
        description: DescriptionProduct,
        supplier: SupplierProduct,
    ) -> ScoreItem:
        points = 10.0 if supplier.sku == "HIGH" else 4.0

        return ScoreItem(
            rule="SKU_TEST",
            points=points,
            maximum=10.0,
            reason=f"Score for {supplier.sku}",
        )

    result = select_candidates(
        description,
        [first_supplier, second_supplier],
        rules=[sku_rule],
    )

    assert result.best_candidate is not None
    assert result.best_candidate.supplier.sku == "HIGH"
    assert result.best_candidate.confidence == 100.0


def test_select_candidates_preserves_order_for_equal_confidence() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    first_supplier = SupplierProduct(
        sku="FIRST",
        name="First supplier",
    )
    second_supplier = SupplierProduct(
        sku="SECOND",
        name="Second supplier",
    )

    def equal_rule(
        description: DescriptionProduct,
        supplier: SupplierProduct,
    ) -> ScoreItem:
        return ScoreItem(
            rule="EQUAL",
            points=5.0,
            maximum=10.0,
            reason="Equal score",
        )

    result = select_candidates(
        description,
        [first_supplier, second_supplier],
        rules=[equal_rule],
    )

    assert tuple(
        candidate.supplier.sku
        for candidate in result.candidates
    ) == (
        "FIRST",
        "SECOND",
    )


def test_select_candidates_accepts_supplier_generator() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )

    suppliers = (
        SupplierProduct(
            sku=str(index),
            name=f"Supplier product {index}",
        )
        for index in range(3)
    )

    result = select_candidates(
        description,
        suppliers,
    )

    assert len(result.candidates) == 3


def test_select_candidates_accepts_rule_generator() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    def full_rule(
        description: DescriptionProduct,
        supplier: SupplierProduct,
    ) -> ScoreItem:
        return ScoreItem(
            rule="FULL",
            points=10.0,
            maximum=10.0,
            reason="Full match",
        )

    rules = (
        rule
        for rule in [full_rule]
    )

    result = select_candidates(
        description,
        [supplier],
        rules=rules,
    )

    assert result.candidates[0].confidence == 100.0