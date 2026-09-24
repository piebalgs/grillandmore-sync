"""Model matching helpers for Weber product matching.

This module keeps model extraction separate from matching strategy.
Exact model identity always has priority over controlled fallback variants.
"""

from __future__ import annotations


def get_model_match_keys(model: str) -> tuple[str, ...]:
    """Return model keys in matching priority order.

    The exact model is always first.

    Genesis models ending in a standalone W variant may fall back to the
    equivalent model without W when no exact WooCommerce model exists.

    Examples:
        GENESIS E-315W   -> ("GENESIS E-315W", "GENESIS E-315")
        GENESIS EPX-435W -> ("GENESIS EPX-435W", "GENESIS EPX-435")
        GENESIS E-330WR  -> ("GENESIS E-330WR",)
    """
    model = model.strip()

    if not model:
        return ()

    keys = [model]

    if model.startswith("GENESIS ") and model.endswith("W"):
        fallback = model[:-1]

        if fallback:
            keys.append(fallback)

    if model == "Q3200N+":
        keys.append("Q3200N")

    return tuple(keys)