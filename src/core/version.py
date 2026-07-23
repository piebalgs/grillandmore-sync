#!/usr/bin/env python3
"""GrillAndMore Sync projekta versijas informācija."""

from __future__ import annotations

from typing import Final


PROJECT_NAME: Final[str] = "GrillAndMore Sync"

VERSION_MAJOR: Final[int] = 0
VERSION_MINOR: Final[int] = 6
VERSION_PATCH: Final[int] = 2

__version__: Final[str] = (
    f"{VERSION_MAJOR}."
    f"{VERSION_MINOR}."
    f"{VERSION_PATCH}"
)

VERSION_INFO: Final[tuple[int, int, int]] = (
    VERSION_MAJOR,
    VERSION_MINOR,
    VERSION_PATCH,
)


def get_version() -> str:
    """Atgriež projekta versiju."""
    return __version__


def get_version_info() -> tuple[int, int, int]:
    """Atgriež versiju kā skaitļu virkni."""
    return VERSION_INFO


def get_full_version() -> str:
    """Atgriež pilnu projekta nosaukumu kopā ar versiju."""
    return f"{PROJECT_NAME} v{__version__}"
