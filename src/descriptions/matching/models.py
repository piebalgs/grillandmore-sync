"""Data models for matching Weber descriptions to supplier products.

This module contains only data structures and lightweight validation.
Matching and scoring logic belongs in separate modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.descriptions.normalizer import normalize_text


class MatchStatus(str, Enum):
    """Possible states of a description-to-product match."""

    AUTO = "AUTO"
    REVIEW = "REVIEW"
    UNMATCHED = "UNMATCHED"
    MANUAL = "MANUAL"


@dataclass(slots=True)
class DescriptionProduct:
    """One shared product-description record loaded from Weber data.

    One description record may be matched to multiple supplier products.

    ``barcode`` stores the Weber-side EAN/GTIN when it is available.
    """

    description_key: str
    title: str = ""
    title_line_1: str = ""
    series: str = ""
    barbecue_code: str = ""
    barcode: str = ""

    normalized_name: str = field(init=False)

    def __post_init__(self) -> None:
        """Clean values, validate required fields and normalize the title."""

        self.description_key = self.description_key.strip()
        self.title = self.title.strip()
        self.title_line_1 = self.title_line_1.strip()
        self.series = self.series.strip()
        self.barbecue_code = self.barbecue_code.strip()
        self.barcode = self.barcode.strip()

        if not self.description_key:
            raise ValueError("description_key must not be empty")

        comparison_title = (
            self.title
            or self.title_line_1
            or self.barbecue_code
            or self.description_key
        )

        self.normalized_name = normalize_text(comparison_title)


@dataclass(slots=True)
class SupplierProduct:
    """One supplier product loaded from XML."""

    sku: str
    name: str
    barcode: str = ""
    producer: str = ""

    normalized_name: str = field(init=False)

    def __post_init__(self) -> None:
        """Clean values, validate required fields and normalize the name."""

        self.sku = self.sku.strip()
        self.name = self.name.strip()
        self.barcode = self.barcode.strip()
        self.producer = self.producer.strip()

        if not self.sku:
            raise ValueError("sku must not be empty")

        if not self.name:
            raise ValueError("name must not be empty")

        self.normalized_name = normalize_text(self.name)


@dataclass(slots=True)
class MatchCandidate:
    """One possible supplier-product match."""

    supplier: SupplierProduct
    confidence: float
    reasons: tuple[str, ...] = field(default_factory=tuple)
    match_type: str = "SCORED"

    def __post_init__(self) -> None:
        """Normalize and validate candidate values."""

        self.confidence = float(self.confidence)
        self.reasons = tuple(
            reason.strip()
            for reason in self.reasons
            if reason and reason.strip()
        )
        self.match_type = self.match_type.strip().upper() or "SCORED"

        if not 0.0 <= self.confidence <= 100.0:
            raise ValueError("confidence must be between 0 and 100")


@dataclass(slots=True)
class MatchResult:
    """Final matching result for one Weber description record."""

    description: DescriptionProduct
    candidates: tuple[MatchCandidate, ...] = field(default_factory=tuple)
    status: MatchStatus = MatchStatus.UNMATCHED
    note: str = ""

    def __post_init__(self) -> None:
        """Normalize values and validate the match status."""

        self.candidates = tuple(self.candidates)
        self.note = self.note.strip()

        if isinstance(self.status, str):
            try:
                self.status = MatchStatus(self.status.upper())
            except ValueError as exc:
                valid_statuses = ", ".join(
                    status.value
                    for status in MatchStatus
                )
                raise ValueError(
                    f"Unknown match status: {self.status}. "
                    f"Expected one of: {valid_statuses}"
                ) from exc

    @property
    def best_candidate(self) -> MatchCandidate | None:
        """Return the candidate with the highest confidence score."""

        if not self.candidates:
            return None

        return max(
            self.candidates,
            key=lambda candidate: candidate.confidence,
        )

    @property
    def is_matched(self) -> bool:
        """Return whether the result contains an accepted match."""

        return (
            self.best_candidate is not None
            and self.status in {
                MatchStatus.AUTO,
                MatchStatus.MANUAL,
            }
        )
