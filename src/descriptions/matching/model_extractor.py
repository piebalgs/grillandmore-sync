"""Product model extraction for description matching.

The extractor identifies the grill model independently from product
configuration wording such as stands, carts, colours, or fuel wording.

Examples:
    "Weber Q 1200N w/stand Gas Grill" -> "Q1200N"
    "Spirit E-325 Gas Grill" -> "SPIRIT E-325"
    "Genesis EX-425W Gas Grill" -> "GENESIS EX-425W"
    "Summit FS38X E Gas Grill" -> "SUMMIT FS38X E"
"""

from __future__ import annotations

import re


_Q_MODEL_RE = re.compile(
    r"\bQ\s*([0-9]{3,4}[A-Z]?)(\+)?(?=\s|$)",
    re.IGNORECASE,
)

_SPIRIT_MODEL_RE = re.compile(
    r"\bSPIRIT\s+"
    r"(EPX|EX|EP|SP|S|E)"
    r"[\s-]*"
    r"([0-9]{3}[A-Z]?)\b",
    re.IGNORECASE,
)

_GENESIS_MODEL_RE = re.compile(
    r"\bGENESIS\s+"
    r"(EPX|EX|EP|SP|S|E)"
    r"[\s-]*"
    r"([0-9]{3}[A-Z]*)\b",
    re.IGNORECASE,
)

_SUMMIT_MODEL_RE = re.compile(
    r"\bSUMMIT\s+"
    r"(FS[0-9]+X?)"
    r"\s*"
    r"([ES])\b",
    re.IGNORECASE,
)


def extract_model(text: str) -> str:
    """Extract a normalized grill model from product text.

    Returns an empty string when no supported model can be identified.
    """
    if not text:
        return ""

    value = _normalize_input(text)

    upper_value = value.upper()

    if re.search(r"\bTRAVELER\s+COMPACT\b", upper_value):
        return "TRAVELER COMPACT"

    if re.search(r"\bTRAVELER\b", upper_value):
        return "TRAVELER"

    if re.search(r"\bGO[-\s]ANYWHERE\b", upper_value):
        return "GO-ANYWHERE"
    match = _Q_MODEL_RE.search(value)
    if match:
        model = f"Q{match.group(1).upper()}"
        if match.group(2):
            model += "+"
        return model

    match = _SPIRIT_MODEL_RE.search(value)
    if match:
        variant = match.group(1).upper()
        number = match.group(2).upper()
        return f"SPIRIT {variant}-{number}"

    match = _GENESIS_MODEL_RE.search(value)
    if match:
        variant = match.group(1).upper()
        number = match.group(2).upper()
        return f"GENESIS {variant}-{number}"

    match = _SUMMIT_MODEL_RE.search(value)
    if match:
        family = match.group(1).upper()
        finish = match.group(2).upper()
        return f"SUMMIT {family} {finish}"

    return ""


def extract_model_from_texts(*texts: str) -> str:
    """Extract the best model found across several text fields.

    The first detected model remains authoritative unless a later field
    contains a more precise Q-series variant of the same base model.

    Examples:
        Q2800N + Q2800N+ -> Q2800N+
        Q3200  + Q3200N+ -> Q3200N+
        Q1200N + Q2200N  -> Q1200N
    """
    models = [
        model
        for text in texts
        if (model := extract_model(text))
    ]

    if not models:
        return ""

    primary = models[0]

    if not primary.startswith("Q"):
        return primary

    for candidate in models[1:]:
        if (
            candidate.startswith(primary)
            and len(candidate) > len(primary)
        ):
            return candidate

    return primary


def _normalize_input(text: str) -> str:
    """Normalize punctuation that may interfere with model extraction."""
    return (
        str(text)
        .replace("®", "")
        .replace("™", "")
        .replace("‐", "-")
        .replace("-", "-")
        .replace("–", "-")
        .replace("—", "-")
        .strip()
    )




