"""Tests for src.descriptions.knowledge_base."""

from datetime import date

import pytest

from src.descriptions.knowledge_base import (
    DuplicateKnowledgeAliasError,
    DuplicateKnowledgeKeyError,
    KnowledgeBase,
    UnknownKnowledgeItemError,
    kb,
)
from src.descriptions.models import KnowledgeCategory, KnowledgeItem


def make_item(
    key: str = "Test Technology",
    *,
    aliases: tuple[str, ...] = (),
    verified: bool = True,
) -> KnowledgeItem:
    return KnowledgeItem(
        key=key,
        category=KnowledgeCategory.TECHNOLOGY,
        translation="Testa tehnoloģija",
        short_description="Īss pārbaudāms apraksts.",
        explanation="Detalizēts pārbaudāms skaidrojums.",
        customer_benefit="Nodrošina pārbaudāmu ieguvumu.",
        aliases=aliases,
        source="Testa avots" if verified else "",
        evidence=("Testa pierādījums",) if verified else (),
        verified=verified,
        last_reviewed=date(2026, 7, 24) if verified else None,
    )


def test_get_by_canonical_key() -> None:
    item = kb.get("Flavorizer Bars")
    assert item.key == "Flavorizer Bars"
    assert item.verified is True


def test_get_is_case_insensitive_and_accepts_alias() -> None:
    item = kb.get("  FLAVORIZER®   BARS ")
    assert item.key == "Flavorizer Bars"


def test_unverified_items_are_hidden_by_default() -> None:
    assert kb.exists("Sear Zone") is False
    with pytest.raises(UnknownKnowledgeItemError):
        kb.get("Sear Zone")


def test_unverified_items_can_be_requested_explicitly() -> None:
    item = kb.get("Sear Zone", include_unverified=True)
    assert item.verified is False


def test_search_matches_translation_and_keywords() -> None:
    results = kb.search("aromatizējošās")
    assert [item.key for item in results] == ["Flavorizer Bars"]


def test_search_can_include_drafts() -> None:
    results = kb.search("aizdedzes", include_unverified=True)
    keys = {item.key for item in results}
    assert "Infinity Ignition" in keys
    assert "Snap-Jet Ignition" in keys


def test_category_filter() -> None:
    results = kb.by_category(KnowledgeCategory.COOKING_SYSTEM)
    assert "Flavorizer Bars" in {item.key for item in results}
    assert all(item.verified for item in results)


def test_duplicate_key_is_rejected() -> None:
    database = KnowledgeBase([make_item()])
    with pytest.raises(DuplicateKnowledgeKeyError):
        database.register(make_item(key=" test technology "))


def test_duplicate_alias_is_rejected() -> None:
    database = KnowledgeBase(
        [make_item(key="First", aliases=("Shared Alias",))]
    )
    with pytest.raises(DuplicateKnowledgeAliasError):
        database.register(
            make_item(key="Second", aliases=("shared alias",))
        )


def test_verified_item_requires_source_evidence_and_date() -> None:
    invalid = KnowledgeItem(
        key="Invalid",
        category=KnowledgeCategory.OTHER,
        translation="Nederīgs",
        short_description="Apraksts.",
        explanation="Skaidrojums.",
        customer_benefit="Ieguvums.",
        verified=True,
    )
    with pytest.raises(ValueError):
        KnowledgeBase([invalid])


def test_related_records_are_resolved() -> None:
    related = kb.related("Flavorizer Bars", include_unverified=True)
    assert [item.key for item in related] == ["Grease Management System"]


def test_all_relations_point_to_registered_items() -> None:
    assert kb.validate_relations() == ()


def test_statistics_are_consistent() -> None:
    stats = kb.statistics()
    assert stats.total == stats.verified + stats.draft
    assert stats.total >= 10
    assert stats.verified >= 1
