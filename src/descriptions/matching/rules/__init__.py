"""Individual scoring rules for product matching."""

from src.descriptions.matching.rules.model_code import (
    MAXIMUM_POINTS as MODEL_CODE_MAXIMUM_POINTS,
)
from src.descriptions.matching.rules.model_code import (
    score_model_code,
)

__all__ = [
    "MODEL_CODE_MAXIMUM_POINTS",
    "score_model_code",
]
