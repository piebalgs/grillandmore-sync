"""Tests for the first complete matching-engine orchestration layer."""

import pytest

from src.descriptions.matching.engine import (
    MatchingEngine,
    MatchingEngineConfig,
    match_description,
    match_descriptions,
)
from src.descriptions.matching.models import (
    DescriptionProduct,
    MatchStatus,
    SupplierProduct,
)
from src.descriptions.matching.score_models import ScoreItem


def score_from_sku(description, supplier):
    del description

    values = {
        "BEST": 100,
        "REVIEW": 85,
        "LOW": 20,
        "ZERO": 0,
    }

    points = values.get(supplier.sku, 0)

    return ScoreItem(
        rule="TEST",
        points=points,
        maximum=100,
        reason=f"Test confidence for {supplier.sku}: {points}",
    )


def make_description(key="SPIRIT_EP_425"):
    return DescriptionProduct(
        description_key=key,
        title="Spirit EP-425",
    )


def make_supplier(sku, name=None):
    return SupplierProduct(
        sku=sku,
        name=name or f"Supplier product {sku}",
        producer="Weber",
    )


def test_config_rejects_invalid_candidate_limit():
    with pytest.raises(ValueError, match="candidate_limit"):
        MatchingEngineConfig(candidate_limit=0)


@pytest.mark.parametrize("value", [-1, 101])
def test_config_rejects_invalid_minimum_confidence(value):
    with pytest.raises(ValueError, match="minimum_confidence"):
        MatchingEngineConfig(minimum_confidence=value)


def test_rank_candidates_orders_highest_confidence_first():
    engine = MatchingEngine(rules=(score_from_sku,))

    ranked = engine.rank_candidates(
        make_description(),
        (
            make_supplier("LOW"),
            make_supplier("BEST"),
            make_supplier("REVIEW"),
        ),
    )

    assert [item.supplier.sku for item in ranked] == [
        "BEST",
        "REVIEW",
        "LOW",
    ]


def test_rank_candidates_respects_candidate_limit():
    engine = MatchingEngine(
        config=MatchingEngineConfig(candidate_limit=2),
        rules=(score_from_sku,),
    )

    ranked = engine.rank_candidates(
        make_description(),
        (
            make_supplier("LOW"),
            make_supplier("BEST"),
            make_supplier("REVIEW"),
        ),
    )

    assert len(ranked) == 2
    assert [item.supplier.sku for item in ranked] == [
        "BEST",
        "REVIEW",
    ]


def test_rank_candidates_filters_minimum_confidence():
    engine = MatchingEngine(
        config=MatchingEngineConfig(minimum_confidence=80),
        rules=(score_from_sku,),
    )

    ranked = engine.rank_candidates(
        make_description(),
        (
            make_supplier("LOW"),
            make_supplier("BEST"),
            make_supplier("REVIEW"),
        ),
    )

    assert [item.supplier.sku for item in ranked] == [
        "BEST",
        "REVIEW",
    ]


def test_match_one_returns_auto_for_best_candidate_at_100():
    engine = MatchingEngine(rules=(score_from_sku,))

    result = engine.match_one(
        make_description(),
        (
            make_supplier("LOW"),
            make_supplier("BEST"),
        ),
    )

    assert result.status is MatchStatus.AUTO
    assert result.best_candidate is not None
    assert result.best_candidate.supplier.sku == "BEST"
    assert result.best_candidate.confidence == 100


def test_match_one_returns_review_for_best_candidate_at_85():
    engine = MatchingEngine(rules=(score_from_sku,))

    result = engine.match_one(
        make_description(),
        (
            make_supplier("LOW"),
            make_supplier("REVIEW"),
        ),
    )

    assert result.status is MatchStatus.REVIEW
    assert result.best_candidate is not None
    assert result.best_candidate.supplier.sku == "REVIEW"


def test_match_one_returns_unmatched_when_no_candidate_survives():
    engine = MatchingEngine(
        config=MatchingEngineConfig(minimum_confidence=50),
        rules=(score_from_sku,),
    )

    result = engine.match_one(
        make_description(),
        (
            make_supplier("LOW"),
            make_supplier("ZERO"),
        ),
    )

    assert result.status is MatchStatus.UNMATCHED
    assert result.best_candidate is None


def test_match_all_reuses_supplier_generator():
    engine = MatchingEngine(rules=(score_from_sku,))

    descriptions = (
        make_description("FIRST"),
        make_description("SECOND"),
    )

    suppliers = (
        supplier
        for supplier in (
            make_supplier("BEST"),
            make_supplier("LOW"),
        )
    )

    results = engine.match_all(descriptions, suppliers)

    assert len(results) == 2
    assert all(
        result.best_candidate is not None
        and result.best_candidate.supplier.sku == "BEST"
        for result in results
    )


def test_convenience_functions():
    description = make_description()
    suppliers = (
        make_supplier("BEST"),
        make_supplier("LOW"),
    )

    single = match_description(
        description,
        suppliers,
        rules=(score_from_sku,),
    )

    multiple = match_descriptions(
        (description,),
        suppliers,
        rules=(score_from_sku,),
    )

    assert single.status is MatchStatus.AUTO
    assert len(multiple) == 1
    assert multiple[0].status is MatchStatus.AUTO
