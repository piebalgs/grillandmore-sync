"""Tests for product title normalization."""

import pytest

from src.descriptions.normalizer import normalize_text


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (None, ""),
        ("", ""),
        ("   ", ""),
        ("Weber Spirit EP-425", "weber spirit ep 425"),
        ("SPIRIT_EP_425", "spirit ep 425"),
        ("Spirit EP425", "spirit ep 425"),
        ("Spirit EP 425", "spirit ep 425"),
        (
            "Weber Spirit EP-425 Gāzes grils, melns",
            "weber spirit ep 425",
        ),
        (
            "Weber Spirit EP-425 Gas Grill Black",
            "weber spirit ep 425",
        ),
        (
            "Weber Genesis E-335®",
            "weber genesis e 335",
        ),
        (
            "WEBER/TRAVELER-BLACK",
            "weber traveler",
        ),
        (
            "Weber Summit E-470™",
            "weber summit e 470",
        ),
        (
            "Weber Q 2200 elektriskais grils",
            "weber q 2200",
        ),
        (
            "Weber Master-Touch GBS E-5750 kokogļu grils",
            "weber master touch gbs e 5750",
        ),
    ],
)
def test_normalize_text(source: str | None, expected: str) -> None:
    assert normalize_text(source) == expected


def test_normalize_text_is_repeatable() -> None:
    source = "Weber Spirit EP-425 Gāzes grils, melns"

    normalized_once = normalize_text(source)
    normalized_twice = normalize_text(normalized_once)

    assert normalized_twice == normalized_once


def test_normalize_text_preserves_model_numbers() -> None:
    assert normalize_text("Genesis E-335") == "genesis e 335"
    assert normalize_text("Spirit EP-425") == "spirit ep 425"
    assert normalize_text("Summit E-470") == "summit e 470"


def test_normalize_text_does_not_modify_input() -> None:
    source = "Weber Spirit EP-425"

    normalize_text(source)

    assert source == "Weber Spirit EP-425"

