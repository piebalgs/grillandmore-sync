"""Tests for the high-level description matcher."""

from __future__ import annotations

from src.descriptions.matching.matcher import match_description
from src.descriptions.matching.models import (
    DescriptionProduct,
    MatchStatus,
    SupplierProduct,
)
from src.descriptions.matching.score_models import ScoreItem


def test_match_description_returns_unmatched_without_suppliers() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )

    result = match_description(
        description,
        [],
    )

    assert result.description is description
    assert result.candidates == ()
    assert result.best_candidate is None
    assert result.status is MatchStatus.UNMATCHED


def test_match_description_returns_auto_for_strong_candidate() -> None:
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

    result = match_description(
        description,
        [supplier],
        rules=[full_rule],
    )

    assert result.status is MatchStatus.AUTO
    assert result.best_candidate is not None
    assert result.best_candidate.supplier is supplier
    assert result.best_candidate.confidence == 100.0


def test_match_description_returns_review_for_medium_candidate() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    def review_rule(
        description: DescriptionProduct,
        supplier: SupplierProduct,
    ) -> ScoreItem:
        return ScoreItem(
            rule="REVIEW",
            points=9.0,
            maximum=10.0,
            reason="Review match",
        )

    result = match_description(
        description,
        [supplier],
        rules=[review_rule],
    )

    assert result.status is MatchStatus.REVIEW
    assert result.best_candidate is not None
    assert result.best_candidate.confidence == 90.0


def test_match_description_returns_unmatched_for_weak_candidate() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    supplier = SupplierProduct(
        sku="1500013",
        name="Unrelated product",
    )

    def weak_rule(
        description: DescriptionProduct,
        supplier: SupplierProduct,
    ) -> ScoreItem:
        return ScoreItem(
            rule="WEAK",
            points=7.0,
            maximum=10.0,
            reason="Weak match",
        )

    result = match_description(
        description,
        [supplier],
        rules=[weak_rule],
    )

    assert result.status is MatchStatus.UNMATCHED
    assert result.best_candidate is not None
    assert result.best_candidate.confidence == 70.0


def test_match_description_ranks_candidates_before_decision() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    weak_supplier = SupplierProduct(
        sku="WEAK",
        name="Weak supplier",
    )
    strong_supplier = SupplierProduct(
        sku="STRONG",
        name="Strong supplier",
    )

    def sku_rule(
        description: DescriptionProduct,
        supplier: SupplierProduct,
    ) -> ScoreItem:
        points = 10.0 if supplier.sku == "STRONG" else 8.0

        return ScoreItem(
            rule="SKU_TEST",
            points=points,
            maximum=10.0,
            reason=f"Score for {supplier.sku}",
        )

    result = match_description(
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

    assert result.best_candidate is not None
    assert result.best_candidate.supplier is strong_supplier
    assert result.status is MatchStatus.AUTO


def test_match_description_preserves_candidate_reasons() -> None:
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
            maximum=5.0,
            reason="First reason",
        )

    def second_rule(
        description: DescriptionProduct,
        supplier: SupplierProduct,
    ) -> ScoreItem:
        return ScoreItem(
            rule="SECOND",
            points=5.0,
            maximum=5.0,
            reason="Second reason",
        )

    result = match_description(
        description,
        [supplier],
        rules=[first_rule, second_rule],
    )

    assert result.best_candidate is not None
    assert result.best_candidate.reasons == (
        "First reason",
        "Second reason",
    )


def test_match_description_accepts_supplier_generator() -> None:
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

    result = match_description(
        description,
        suppliers,
    )

    assert len(result.candidates) == 3


def test_match_description_accepts_rule_generator() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )
    suppliers = [
        SupplierProduct(
            sku="FIRST",
            name="First supplier",
        ),
        SupplierProduct(
            sku="SECOND",
            name="Second supplier",
        ),
    ]

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

    result = match_description(
        description,
        suppliers,
        rules=rules,
    )

    assert len(result.candidates) == 2
    assert all(
        candidate.confidence == 100.0
        for candidate in result.candidates
    )