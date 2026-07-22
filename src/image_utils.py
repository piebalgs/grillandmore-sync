#!/usr/bin/env python3

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


def normalize_sku(value: Any) -> str:
    """Atgriež normalizētu SKU salīdzināšanai."""
    return str(value or "").strip().upper()


def filename_from_url(url: Any) -> str:
    """Droši iegūst faila nosaukumu no URL."""
    text = str(url or "").strip()

    if not text:
        return ""

    parsed = urlparse(text)
    return Path(unquote(parsed.path)).name


def normalize_filename(value: Any) -> str:
    """
    Izveido stabilu attēla atslēgu neatkarīgi no paplašinājuma,
    WordPress izmēra sufiksa un atstarpju/defišu atšķirībām.
    """
    text = unquote(str(value or "")).strip()

    if not text:
        return ""

    text = text.split("?", 1)[0]
    text = text.split("#", 1)[0]
    text = Path(text).name

    stem = Path(text).stem.upper()
    stem = re.sub(r"-SCALED$", "", stem)
    stem = re.sub(r"-\d+$", "", stem)
    stem = re.sub(r"[\s_-]+", "", stem)

    return stem


def image_key(image: dict[str, Any]) -> str:
    """Atgriež attēla normalizēto identifikācijas atslēgu."""
    return normalize_filename(
        image.get("filename")
        or image.get("name")
        or filename_from_url(
            image.get("src")
            or image.get("url")
        )
    )


def safe_position(image: dict[str, Any]) -> int:
    """Atgriež Brandfolder pozīciju vai drošu rezerves vērtību."""
    try:
        return int(image.get("position", 9999))
    except (TypeError, ValueError):
        return 9999


def image_priority(image: dict[str, Any]) -> tuple[Any, ...]:
    """
    Sakārto Brandfolder attēlus produkta galerijai.

    Prioritāte:
      1. A / FRONT / galvenais produkta skats
      2. OPEN skati
      3. B / LEFT
      4. C / RIGHT
      5. D / BACK
      6. DETAIL / tuvplāni
      7. pārējie produkta skati
      8. M1, M2... lifestyle attēli
    """
    filename = str(
        image.get("filename")
        or image.get("name")
        or filename_from_url(
            image.get("src")
            or image.get("url")
        )
        or ""
    ).strip()

    name = Path(filename).stem.upper()

    is_lifestyle = bool(
        re.search(r"(?:^|[^A-Z0-9])M\d+(?:[^A-Z0-9]|$)", name)
        or re.search(r"\dM\d+(?:[^A-Z0-9]|$)", name)
    )

    if is_lifestyle:
        group = 90
    elif "FRONT" in name or re.search(
        r"(?:^|[_\s.-])A(?:\d+)?(?:[_\s.-]|$)",
        name,
    ):
        group = 10
    elif "OPEN" in name:
        group = 20
    elif "LEFT" in name or re.search(
        r"(?:^|[_\s.-])B(?:\d+)?(?:[_\s.-]|$)",
        name,
    ):
        group = 30
    elif "RIGHT" in name or re.search(
        r"(?:^|[_\s.-])C(?:\d+)?(?:[_\s.-]|$)",
        name,
    ):
        group = 40
    elif "BACK" in name or re.search(
        r"(?:^|[_\s.-])D(?:\d+)?(?:[_\s.-]|$)",
        name,
    ):
        group = 50
    elif any(
        marker in name
        for marker in ("DETAIL", "CLOSE", "CLOSEUP", "ZOOM")
    ):
        group = 60
    else:
        group = 70

    return (
        group,
        safe_position(image),
        name,
    )


def deduplicate_brandfolder_images(
    images: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Noņem Brandfolder dublikātus un sakārto attēlus prioritārā secībā."""
    unique: dict[str, dict[str, Any]] = {}

    for image in images:
        if not isinstance(image, dict):
            continue

        key = image_key(image)

        if not key:
            continue

        current = unique.get(key)

        if current is None or image_priority(image) < image_priority(current):
            unique[key] = image

    result = list(unique.values())
    result.sort(key=image_priority)
    return result


def existing_woocommerce_keys(
    images: list[dict[str, Any]],
) -> set[str]:
    """Atgriež visas WooCommerce attēlu normalizētās atslēgas."""
    keys: set[str] = set()

    for image in images:
        if not isinstance(image, dict):
            continue

        candidates = [
            image.get("name"),
            image.get("alt"),
            filename_from_url(image.get("src")),
        ]

        for candidate in candidates:
            key = normalize_filename(candidate)

            if key:
                keys.add(key)

    return keys


def display_filename(image: dict[str, Any]) -> str:
    """Atgriež cilvēkam lasāmu attēla faila nosaukumu."""
    return str(
        image.get("filename")
        or image.get("name")
        or filename_from_url(image.get("src"))
        or filename_from_url(image.get("url"))
        or ""
    )
