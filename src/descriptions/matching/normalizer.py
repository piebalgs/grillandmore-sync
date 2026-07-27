"""Normalization helpers for product matching.

The general description normalizer remains responsible for cleaning product
text. This module builds additional comparison forms required by the matching
and scoring subsystems.

No matching decisions or confidence calculations belong in this module.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.descriptions.normalizer import normalize_text


@dataclass(frozen=True, slots=True)
class NormalizedText:
    """Different normalized representations of one product name.

    Attributes:
        original:
            Original input value after surrounding whitespace is removed.

        text:
            Product text normalized by the existing description normalizer.

        tokens:
            Ordered normalized words and numbers.

        unique_tokens:
            Ordered tokens without duplicates.

        alpha_tokens:
            Tokens containing only letters.

        numeric_tokens:
            Tokens containing only digits.

        compact:
            Normalized text without spaces. This is useful when comparing
            differently formatted model codes such as ``EP-425`` and
            ``EP425``.
    """

    original: str
    text: str
    tokens: tuple[str, ...]
    unique_tokens: tuple[str, ...]
    alpha_tokens: tuple[str, ...]
    numeric_tokens: tuple[str, ...]
    compact: str

    @property
    def is_empty(self) -> bool:
        """Return whether normalization produced no comparison text."""
        return not self.text


def _unique_in_order(values: tuple[str, ...]) -> tuple[str, ...]:
    """Return values without duplicates while preserving their order."""
    return tuple(dict.fromkeys(values))


def normalize_product_name(value: str | None) -> NormalizedText:
    """Build matcher-friendly comparison forms for a product name.

    ``None`` and whitespace-only values are accepted and converted into an
    empty normalized representation.

    Args:
        value:
            Raw product name, model name or description key.

    Returns:
        Immutable normalized comparison data.
    """
    original = "" if value is None else str(value).strip()

    if not original:
        return NormalizedText(
            original="",
            text="",
            tokens=(),
            unique_tokens=(),
            alpha_tokens=(),
            numeric_tokens=(),
            compact="",
        )

    text = normalize_text(original).strip()
    tokens = tuple(token for token in text.split() if token)

    return NormalizedText(
        original=original,
        text=text,
        tokens=tokens,
        unique_tokens=_unique_in_order(tokens),
        alpha_tokens=tuple(
            token
            for token in tokens
            if token.isalpha()
        ),
        numeric_tokens=tuple(
            token
            for token in tokens
            if token.isdigit()
        ),
        compact="".join(tokens),
    )


def normalize_match_text(value: str | None) -> str:
    """Return only the normalized comparison text."""
    return normalize_product_name(value).text


def match_tokens(value: str | None) -> tuple[str, ...]:
    """Return ordered normalized comparison tokens."""
    return normalize_product_name(value).tokens


def unique_match_tokens(value: str | None) -> tuple[str, ...]:
    """Return normalized comparison tokens without duplicates."""
    return normalize_product_name(value).unique_tokens


def compact_match_text(value: str | None) -> str:
    """Return normalized comparison text without spaces."""
    return normalize_product_name(value).compact
