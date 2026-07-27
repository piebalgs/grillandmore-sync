"""Individual scoring rules for product matching."""

from src.descriptions.matching.rules.model_code import (
    MAXIMUM_POINTS as MODEL_CODE_MAXIMUM_POINTS,
    score_model_code,
)
from src.descriptions.matching.rules.producer import score_producer
from src.descriptions.matching.rules.series import score_series
from src.descriptions.matching.rules.title_similarity import (
    MAXIMUM_POINTS as TITLE_SIMILARITY_MAXIMUM_POINTS,
    score_title_similarity,
)

__all__ = [
    "MODEL_CODE_MAXIMUM_POINTS",
    "TITLE_SIMILARITY_MAXIMUM_POINTS",
    "score_model_code",
    "score_series",
    "score_producer",
    "score_title_similarity",
]