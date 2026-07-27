"""Tests for product matching normalization helpers."""

import pytest

from src.descriptions.matching.normalizer import (
    NormalizedText,
    compact_match_text,
    match_tokens,
    normalize_match_text,
    normalize_product_name,
    unique_match_tokens,
)


def test_normalize_product_name_returns_normalized_text_model() -> None:
    result = normalize_product_name(
        "Weber Spirit EP-425 Gāzes grils, melns"
    )

    assert isinstance(result, NormalizedText)
    assert result.original == (
        "Weber Spirit EP-425 Gāzes grils, melns"
    )
    assert result.text == "weber spirit ep 425"


def test_normalize_product_name_builds_ordered_tokens() -> None:
    result = normalize_product_name(
        "Weber Spirit EP-425 Gāzes grils, melns"
    )

    assert result.tokens == (
        "weber",
        "spirit",
        "ep",
        "425",
    )


def test_normalize_product_name_builds_unique_tokens() -> None:
    result = normalize_product_name(
        "Spirit Spirit EP-425 EP-425"
    )

    assert result.tokens == (
        "spirit",
        "spirit",
        "ep",
        "425",
        "ep",
        "425",
    )
    assert result.unique_tokens == (
        "spirit",
        "ep",
        "425",
    )


def test_normalize_product_name_splits_alpha_and_numeric_tokens() -> None:
    result = normalize_product_name(
        "Weber Genesis E-335"
    )

    assert result.alpha_tokens == (
        "weber",
        "genesis",
        "e",
    )
    assert result.numeric_tokens == ("335",)


def test_normalize_product_name_builds_compact_form() -> None:
    result = normalize_product_name(
        "Weber Spirit EP-425"
    )

    assert result.compact == "weberspiritep425"


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
    ],
)
def test_normalize_product_name_accepts_empty_values(
    value: str | None,
) -> None:
    result = normalize_product_name(value)

    assert result.original == ""
    assert result.text == ""
    assert result.tokens == ()
    assert result.unique_tokens == ()
    assert result.alpha_tokens == ()
    assert result.numeric_tokens == ()
    assert result.compact == ""
    assert result.is_empty is True


def test_normalized_product_name_is_not_empty() -> None:
    result = normalize_product_name(
        "Genesis E-335"
    )

    assert result.is_empty is False


def test_normalized_text_is_immutable() -> None:
    result = normalize_product_name(
        "Genesis E-335"
    )

    with pytest.raises(AttributeError):
        result.text = "changed"


def test_normalize_match_text_returns_only_text() -> None:
    assert (
        normalize_match_text(
            "Weber Spirit EP-425 Gāzes grils, melns"
        )
        == "weber spirit ep 425"
    )


def test_match_tokens_returns_token_tuple() -> None:
    assert match_tokens(
        "Genesis E-335"
    ) == (
        "genesis",
        "e",
        "335",
    )


def test_unique_match_tokens_removes_duplicates() -> None:
    assert unique_match_tokens(
        "Spirit Spirit EP-425"
    ) == (
        "spirit",
        "ep",
        "425",
    )


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("EP-425", "EP425"),
        ("E-335", "E335"),
        ("SPIRIT_EP_425", "SPIRIT EP 425"),
    ],
)
def test_compact_form_handles_model_code_formatting(
    left: str,
    right: str,
) -> None:
    assert compact_match_text(left) == compact_match_text(right)


def test_compact_match_text_returns_empty_string_for_none() -> None:
    assert compact_match_text(None) == ""


def test_normalization_preserves_original_without_outer_whitespace() -> None:
    result = normalize_product_name(
        "  Weber Genesis E-335  "
    )

    assert result.original == "Weber Genesis E-335"


def test_numeric_tokens_preserve_multiple_numbers() -> None:
    result = normalize_product_name(
        "Weber Summit E-470 4 degļi"
    )

    assert result.numeric_tokens == (
        "470",
        "4",
    )


def test_unique_tokens_preserve_first_occurrence_order() -> None:
    result = normalize_product_name(
        "Genesis E-335 Genesis Weber E-335"
    )

    assert result.unique_tokens == (
        "genesis",
        "e",
        "335",
        "weber",
    )
