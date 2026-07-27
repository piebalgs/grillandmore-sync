"""Data models for explainable product-match scoring.

This module contains only immutable scoring result structures. The actual
comparison rules and point calculations belong in ``scoring.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True, slots=True)
class ScoreItem:
    """Result produced by one scoring rule.

    Attributes:
        rule:
            Stable technical rule identifier, for example ``MODEL_CODE``.

        points:
            Points awarded by the rule.

        maximum:
            Maximum number of points available from the rule.

        reason:
            Human-readable explanation of the result.
    """

    rule: str
    points: float
    maximum: float
    reason: str

    def __post_init__(self) -> None:
        """Normalize and validate the scoring item."""
        rule = self.rule.strip().upper()
        reason = self.reason.strip()
        points = float(self.points)
        maximum = float(self.maximum)

        if not rule:
            raise ValueError("rule must not be empty")

        if not reason:
            raise ValueError("reason must not be empty")

        if maximum <= 0:
            raise ValueError("maximum must be greater than 0")

        if points < 0:
            raise ValueError("points must not be negative")

        if points > maximum:
            raise ValueError("points must not exceed maximum")

        object.__setattr__(self, "rule", rule)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "maximum", maximum)

    @property
    def ratio(self) -> float:
        """Return the awarded share as a value from 0.0 to 1.0."""
        return self.points / self.maximum

    @property
    def percentage(self) -> float:
        """Return the awarded share as a percentage."""
        return self.ratio * 100.0

    @property
    def is_full_match(self) -> bool:
        """Return whether the rule awarded all available points."""
        return self.points == self.maximum

    @property
    def has_points(self) -> bool:
        """Return whether the rule awarded any points."""
        return self.points > 0


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """Combined output from multiple scoring rules.

    The confidence value is calculated from awarded points relative to the
    maximum available points:

        confidence = total / maximum * 100

    Attributes:
        items:
            Individual rule results.

        total:
            Total awarded points.

        maximum:
            Total available points.

        confidence:
            Normalized score from 0.0 to 100.0.
    """

    items: tuple[ScoreItem, ...] = field(default_factory=tuple)

    total: float = field(init=False)
    maximum: float = field(init=False)
    confidence: float = field(init=False)

    def __post_init__(self) -> None:
        """Convert items to a tuple and calculate score totals."""
        items = tuple(self.items)

        total = sum(item.points for item in items)
        maximum = sum(item.maximum for item in items)

        confidence = (
            total / maximum * 100.0
            if maximum > 0
            else 0.0
        )

        object.__setattr__(self, "items", items)
        object.__setattr__(self, "total", total)
        object.__setattr__(self, "maximum", maximum)
        object.__setattr__(self, "confidence", confidence)

    @classmethod
    def from_items(
        cls,
        items: Iterable[ScoreItem],
    ) -> ScoreResult:
        """Create a score result from any iterable of score items."""
        return cls(items=tuple(items))

    @property
    def is_empty(self) -> bool:
        """Return whether the result contains no scoring items."""
        return not self.items

    @property
    def reasons(self) -> tuple[str, ...]:
        """Return human-readable explanations in rule order."""
        return tuple(item.reason for item in self.items)

    @property
    def matched_rules(self) -> tuple[str, ...]:
        """Return identifiers of rules that awarded points."""
        return tuple(
            item.rule
            for item in self.items
            if item.has_points
        )

    @property
    def full_match_rules(self) -> tuple[str, ...]:
        """Return identifiers of rules that awarded maximum points."""
        return tuple(
            item.rule
            for item in self.items
            if item.is_full_match
        )

    def get_item(self, rule: str) -> ScoreItem | None:
        """Return the item for a rule identifier, when present."""
        normalized_rule = rule.strip().upper()

        for item in self.items:
            if item.rule == normalized_rule:
                return item

        return None
