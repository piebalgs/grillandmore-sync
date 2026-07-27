"""Product title normalization utilities.

This module converts product titles from different data sources into a
consistent representation suitable for comparison.

Normalization must remain conservative: meaningful model information should
not be removed.
"""

from __future__ import annotations

import re
import unicodedata


# Words that usually describe the product type rather than the exact model.
#
# These are removed only as complete phrases or words. Model identifiers,
# series names and numbers must remain untouched.
_REMOVABLE_PHRASES: tuple[str, ...] = (
    "gāzes grils",
    "gazes grils",
    "gas barbecue",
    "gas grill",
    "kokogļu grils",
    "kokoglu grils",
    "charcoal barbecue",
    "charcoal grill",
    "elektriskais grils",
    "electric barbecue",
    "electric grill",
)


# Common colour, material and trademark words.
#
# Colour will later be extracted separately by the matcher. For the basic
# normalized title, it is useful to remove it so that colour variants of the
# same model can still be identified as related products.
_REMOVABLE_WORDS: frozenset[str] = frozenset(
    {
        "black",
        "melns",
        "melna",
        "melnais",
        "stainless",
        "inox",
        "nerūsējošs",
        "nerusejoss",
        "steel",
        "tērauds",
        "terauds",
        "tm",
    }
)


def normalize_text(value: str | None) -> str:
    """Return a normalized form of a product title.

    The function:

    - handles empty values;
    - removes trademark symbols;
    - converts Unicode text into a consistent form;
    - converts text to lowercase;
    - separates letters from numbers where appropriate;
    - replaces punctuation with spaces;
    - removes selected generic product phrases;
    - removes selected colour, material and trademark words;
    - collapses repeated whitespace.

    Meaningful model information is preserved.

    Examples:
        >>> normalize_text("Weber Spirit EP-425 Gāzes grils, melns")
        'weber spirit ep 425'

        >>> normalize_text("SPIRIT EP425 Black")
        'spirit ep 425'
    """
    if value is None:
        return ""

    text = str(value).strip()

    if not text:
        return ""

    # Trademark symbols must be removed before NFKC normalization.
    #
    # NFKC can convert:
    #     ™ -> TM
    #
    # If the symbols were removed afterwards, "tm" could remain in the
    # normalized product title.
    text = text.replace("®", " ")
    text = text.replace("™", " ")
    text = text.replace("©", " ")

    text = unicodedata.normalize("NFKC", text)
    text = text.casefold()

    # EP425 -> EP 425
    # E335  -> E 335
    text = re.sub(r"(?<=[a-z])(?=\d)", " ", text)

    # 425S -> 425 S
    text = re.sub(r"(?<=\d)(?=[a-z])", " ", text)

    # Convert punctuation and separators into spaces.
    text = re.sub(r"[_/\\|,+;:()[\]{}]", " ", text)
    text = re.sub(r"[-–—]", " ", text)

    # Remove generic multi-word phrases before processing individual words.
    for phrase in sorted(_REMOVABLE_PHRASES, key=len, reverse=True):
        pattern = rf"\b{re.escape(phrase)}\b"
        text = re.sub(pattern, " ", text)

    words = [
        word
        for word in text.split()
        if word not in _REMOVABLE_WORDS
    ]

    return " ".join(words)