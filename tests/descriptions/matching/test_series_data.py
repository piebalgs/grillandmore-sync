"""Tests for Weber product-series configuration."""

from src.descriptions.matching.data.series import SERIES_NAMES


def test_series_names_is_tuple() -> None:
    assert isinstance(SERIES_NAMES, tuple)


def test_series_names_is_not_empty() -> None:
    assert SERIES_NAMES


def test_series_names_contains_expected_core_series() -> None:
    expected_series = {
        "SPIRIT",
        "GENESIS",
        "SUMMIT",
        "TRAVELER",
        "Q",
    }

    assert expected_series.issubset(set(SERIES_NAMES))


def test_series_names_are_non_empty_strings() -> None:
    assert all(
        isinstance(series, str) and series.strip()
        for series in SERIES_NAMES
    )


def test_series_names_are_uppercase() -> None:
    assert all(
        series == series.upper()
        for series in SERIES_NAMES
    )


def test_series_names_have_no_outer_whitespace() -> None:
    assert all(
        series == series.strip()
        for series in SERIES_NAMES
    )


def test_series_names_have_no_exact_duplicates() -> None:
    assert len(SERIES_NAMES) == len(set(SERIES_NAMES))


def test_known_multiword_series_are_present() -> None:
    assert "SMOKEY JOE" in SERIES_NAMES
    assert "SMOKEY MOUNTAIN" in SERIES_NAMES
    assert "MASTER TOUCH" in SERIES_NAMES
    assert "GO ANYWHERE" in SERIES_NAMES
