"""Individual scoring rules for product matching."""

from src.descriptions.matching.rules.model_code import (
    MAXIMUM_POINTS as MODEL_CODE_MAXIMUM_POINTS,
    score_model_code,
)
from src.descriptions.matching.rules.producer import score_producer
from src.descriptions.matching.rules.series import score_series


__all__ = [
    "MODEL_CODE_MAXIMUM_POINTS",
    "score_model_code",
    "score_producer",
    "score_series",
]