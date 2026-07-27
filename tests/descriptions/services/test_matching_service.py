"""Tests for MatchingService."""

from __future__ import annotations

from src.descriptions.matching.models import (
    DescriptionProduct,
    MatchStatus,
    SupplierProduct,
)
from src.descriptions.matching.score_models import ScoreItem
from src.descriptions.services.matching_service import MatchingService


def test_match_returns_tuple() -> None:
    service = MatchingService()

    results = service.match([], [])

    assert isinstance(results, tuple)


def test_match_returns_empty_tuple() -> None:
    service = MatchingService()

    results = service.match([], [])

    assert results == ()


def test_match_matches_every_description() -> None:
    descriptions = [
        DescriptionProduct(description_key="FIRST"),
        DescriptionProduct(description_key="SECOND"),
    ]

    supplier = SupplierProduct(
        sku="SKU1",
        name="Weber Spirit",
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

    service = MatchingService()

    results = service.match(
        descriptions,
        [supplier],
        rules=[full_rule],
    )

    assert len(results) == 2
    assert all(
        result.status is MatchStatus.AUTO
        for result in results
    )


def test_match_accepts_generators() -> None:
    descriptions = (
        DescriptionProduct(description_key=f"D{i}")
        for i in range(3)
    )

    suppliers = (
        SupplierProduct(
            sku=str(i),
            name=f"Supplier {i}",
        )
        for i in range(2)
    )

    service = MatchingService()

    results = service.match(
        descriptions,
        suppliers,
    )

    assert len(results) == 3