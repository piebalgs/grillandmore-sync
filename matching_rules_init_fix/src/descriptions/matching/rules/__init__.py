"""Individual scoring rules for product matching."""

from src.descriptions.matching.rules.ean import (
    normalize_barcode,
    score_ean,
)
from src.descriptions.matching.rules.model_code import score_model_code
from src.descriptions.matching.rules.producer import score_producer
from src.descriptions.matching.rules.series import score_series
from src.descriptions.matching.rules.title_similarity import (
    score_title_similarity,
)

__all__ = [
    "normalize_barcode",
    "score_ean",
    "score_model_code",
    "score_producer",
    "score_series",
    "score_title_similarity",
]
