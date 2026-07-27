"""Data models for explainable product-match scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class RuleStatus(str, Enum):
    """Semantic outcome returned by one matching expert."""

    MATCH = "MATCH"
    NO_MATCH = "NO_MATCH"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class ScoreItem:
    """Result produced by one scoring rule.

    ``UNKNOWN`` means that the rule had insufficient data and therefore its
    maximum points are excluded from confidence calculation.

    ``CONFLICT`` means that both values existed but contradicted each other.
    Conflict handling can later be extended with explicit penalties without
    changing the rule interface.
    """

    rule: str
    points: float
    maximum: float
    reason: str
    status: RuleStatus | str | None = None

    def __post_init__(self) -> None:
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

        status = self.status
        if status is None:
            status = (
                RuleStatus.MATCH
                if points > 0
                else RuleStatus.NO_MATCH
            )
        elif isinstance(status, str):
            try:
                status = RuleStatus(status.strip().upper())
            except ValueError as exc:
                valid = ", ".join(item.value for item in RuleStatus)
                raise ValueError(
                    f"Unknown rule status: {status}. "
                    f"Expected one of: {valid}"
                ) from exc

        if status is RuleStatus.MATCH and points <= 0:
            raise ValueError("MATCH status must award points")

        if status in {
            RuleStatus.UNKNOWN,
            RuleStatus.CONFLICT,
            RuleStatus.NO_MATCH,
        } and points != 0:
            raise ValueError(
                f"{status.value} status must award 0 points"
            )

        object.__setattr__(self, "rule", rule)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "maximum", maximum)
        object.__setattr__(self, "status", status)

    @property
    def ratio(self) -> float:
        return self.points / self.maximum

    @property
    def percentage(self) -> float:
        return self.ratio * 100.0

    @property
    def is_full_match(self) -> bool:
        return (
            self.status is RuleStatus.MATCH
            and self.points == self.maximum
        )

    @property
    def has_points(self) -> bool:
        return self.points > 0

    @property
    def is_applicable(self) -> bool:
        """Return whether this rule had enough data to evaluate."""

        return self.status is not RuleStatus.UNKNOWN


@dataclass(frozen=True, slots=True)
class ScoreResult:
    """Combined output from multiple scoring rules."""

    items: tuple[ScoreItem, ...] = field(default_factory=tuple)

    total: float = field(init=False)
    maximum: float = field(init=False)
    confidence: float = field(init=False)

    def __post_init__(self) -> None:
        items = tuple(self.items)
        applicable = tuple(
            item for item in items
            if item.is_applicable
        )

        total = sum(item.points for item in applicable)
        maximum = sum(item.maximum for item in applicable)
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
    ) -> "ScoreResult":
        return cls(items=tuple(items))

    @property
    def is_empty(self) -> bool:
        return not self.items

    @property
    def reasons(self) -> tuple[str, ...]:
        return tuple(item.reason for item in self.items)

    @property
    def matched_rules(self) -> tuple[str, ...]:
        return tuple(
            item.rule
            for item in self.items
            if item.status is RuleStatus.MATCH
        )

    @property
    def full_match_rules(self) -> tuple[str, ...]:
        return tuple(
            item.rule
            for item in self.items
            if item.is_full_match
        )

    @property
    def unknown_rules(self) -> tuple[str, ...]:
        return tuple(
            item.rule
            for item in self.items
            if item.status is RuleStatus.UNKNOWN
        )

    @property
    def conflict_rules(self) -> tuple[str, ...]:
        return tuple(
            item.rule
            for item in self.items
            if item.status is RuleStatus.CONFLICT
        )

    def get_item(self, rule: str) -> ScoreItem | None:
        normalized_rule = rule.strip().upper()

        for item in self.items:
            if item.rule == normalized_rule:
                return item

        return None
