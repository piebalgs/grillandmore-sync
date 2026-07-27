"""Tests for batch description matching."""

from __future__ import annotations

from src.descriptions.matching.match_all import match_all
from src.descriptions.matching.models import (
    DescriptionProduct,
    MatchStatus,
    SupplierProduct,
)
from src.descriptions.matching.score_models import ScoreItem


def test_match_all_returns_empty_tuple_without_descriptions() -> None:
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    results = match_all(
        [],
        [supplier],
    )

    assert results == ()


def test_match_all_returns_one_result_per_description() -> None:
    descriptions = [
        DescriptionProduct(
            description_key="FIRST",
        ),
        DescriptionProduct(
            description_key="SECOND",
        ),
    ]
    supplier = SupplierProduct(
        sku="1500013",
        name="Weber Spirit EP-425",
    )

    results = match_all(
        descriptions,
        [supplier],
    )

    assert len(results) == 2


def test_match_all_preserves_description_order() -> None:
    first = DescriptionProduct(
        description_key="FIRST",
    )
    second = DescriptionProduct(
        description_key="SECOND",
    )
    third = DescriptionProduct(
        description_key="THIRD",
    )

    results = match_all(
        [first, second, third],
        [],
    )

    assert tuple(
        result.description
        for result in results
    ) == (
        first,
        second,
        third,
    )


def test_match_all_returns_unmatched_without_suppliers() -> None:
    descriptions = [
        DescriptionProduct(
            description_key="FIRST",
        ),
        DescriptionProduct(
            description_key="SECOND",
        ),
    ]

    results = match_all(
        descriptions,
        [],
    )

    assert all(
        result.status is MatchStatus.UNMATCHED
        for result in results
    )
    assert all(
        result.candidates == ()
        for result in results
    )


def test_match_all_matches_every_description() -> None:
    descriptions = [
        DescriptionProduct(
            description_key="SPIRIT_EP_425",
        ),
        DescriptionProduct(
            description_key="GENESIS_E_325",
        ),
    ]
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
            reason="Full test match",
        )

    results = match_all(
        descriptions,
        [supplier],
        rules=[full_rule],
    )

    assert len(results) == 2
    assert all(
        result.status is MatchStatus.AUTO
        for result in results
    )
    assert all(
        result.best_candidate is not None
        for result in results
    )


def test_match_all_uses_same_suppliers_for_every_description() -> None:
    descriptions = [
        DescriptionProduct(
            description_key="FIRST",
        ),
        DescriptionProduct(
            description_key="SECOND",
        ),
    ]
    suppliers = [
        SupplierProduct(
            sku="A",
            name="Supplier A",
        ),
        SupplierProduct(
            sku="B",
            name="Supplier B",
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
            reason="Full test match",
        )

    results = match_all(
        descriptions,
        suppliers,
        rules=[full_rule],
    )

    assert tuple(
        len(result.candidates)
        for result in results
    ) == (
        2,
        2,
    )


def test_match_all_accepts_description_generator() -> None:
    descriptions = (
        DescriptionProduct(
            description_key=f"DESCRIPTION_{index}",
        )
        for index in range(3)
    )

    results = match_all(
        descriptions,
        [],
    )

    assert len(results) == 3


def test_match_all_reuses_supplier_generator() -> None:
    descriptions = [
        DescriptionProduct(
            description_key="FIRST",
        ),
        DescriptionProduct(
            description_key="SECOND",
        ),
    ]

    suppliers = (
        SupplierProduct(
            sku=str(index),
            name=f"Supplier product {index}",
        )
        for index in range(3)
    )

    results = match_all(
        descriptions,
        suppliers,
    )

    assert tuple(
        len(result.candidates)
        for result in results
    ) == (
        3,
        3,
    )


def test_match_all_reuses_rule_generator() -> None:
    descriptions = [
        DescriptionProduct(
            description_key="FIRST",
        ),
        DescriptionProduct(
            description_key="SECOND",
        ),
    ]
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
            reason="Full test match",
        )

    rules = (
        rule
        for rule in [full_rule]
    )

    results = match_all(
        descriptions,
        [supplier],
        rules=rules,
    )

    assert all(
        result.status is MatchStatus.AUTO
        for result in results
    )
    assert all(
        result.best_candidate is not None
        and result.best_candidate.confidence == 100.0
        for result in results
    )


def test_match_all_preserves_candidate_ranking_per_description() -> None:
    descriptions = [
        DescriptionProduct(
            description_key="FIRST",
        ),
        DescriptionProduct(
            description_key="SECOND",
        ),
    ]
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

    results = match_all(
        descriptions,
        [weak_supplier, strong_supplier],
        rules=[sku_rule],
    )

    assert all(
        tuple(
            candidate.supplier.sku
            for candidate in result.candidates
        )
        == (
            "STRONG",
            "WEAK",
        )
        for result in results
    )


def test_match_all_returns_tuple() -> None:
    description = DescriptionProduct(
        description_key="SPIRIT_EP_425",
    )

    results = match_all(
        [description],
        [],
    )

    assert isinstance(results, tuple)