#!/usr/bin/env python3
"""WooCommerce un Brandfolder attēlu sinhronizācijas plānotājs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from src.core.config import settings


MAX_IMAGES_PER_PRODUCT = settings.max_images_per_product


def normalize_sku(value: Any) -> str:
    """Normalizē SKU salīdzināšanai."""
    return str(value or "").strip().upper()


def filename_from_url(url: Any) -> str:
    """Atgriež faila nosaukumu no URL adreses."""
    text = str(url or "").strip()

    if not text:
        return ""

    parsed = urlparse(text)

    return Path(
        unquote(parsed.path)
    ).name


def normalize_filename(value: Any) -> str:
    """
    Normalizē attēla faila nosaukumu salīdzināšanai.

    Tiek noņemts:
      - URL query un fragment daļas;
      - mapes ceļš;
      - faila paplašinājums;
      - WordPress -scaled sufikss;
      - WordPress automātiski pievienotais skaitļa sufikss;
      - atstarpes, defises un pasvītrojumi.

    Rezultāts tiek pārveidots uz lielajiem burtiem.
    """
    text = unquote(
        str(value or "")
    ).strip()

    if not text:
        return ""

    text = text.split(
        "?",
        1,
    )[0]

    text = text.split(
        "#",
        1,
    )[0]

    text = Path(text).name

    stem = Path(text).stem.upper()

    stem = re.sub(
        r"-SCALED$",
        "",
        stem,
    )

    stem = re.sub(
        r"-\d+$",
        "",
        stem,
    )

    stem = re.sub(
        r"[\s_-]+",
        "",
        stem,
    )

    return stem


def image_key(
    image: dict[str, Any],
) -> str:
    """
    Izveido attēla salīdzināšanas atslēgu.

    Prioritārā secība:
      1. filename;
      2. name;
      3. src vai url adreses faila nosaukums.
    """
    return normalize_filename(
        image.get("filename")
        or image.get("name")
        or filename_from_url(
            image.get("src")
            or image.get("url")
        )
    )


def safe_position(
    image: dict[str, Any],
) -> int:
    """Droši nolasa Brandfolder attēla pozīciju."""
    try:
        return int(
            image.get(
                "position",
                9999,
            )
        )
    except (TypeError, ValueError):
        return 9999


def image_priority(
    image: dict[str, Any],
) -> tuple[Any, ...]:
    """
    Izveido Brandfolder attēla kārtošanas prioritāti.

    Prioritāte:
      1. A / FRONT / galvenais produkta skats;
      2. OPEN skati;
      3. B / LEFT;
      4. C / RIGHT;
      5. D / BACK;
      6. DETAIL / tuvplāni;
      7. pārējie produkta skati;
      8. M1, M2 un citi lifestyle attēli.

    Brandfolder position tiek izmantota kā papildu
    kārtošanas pazīme.
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
        re.search(
            r"(?:^|[^A-Z0-9])M\d+(?:[^A-Z0-9]|$)",
            name,
        )
        or re.search(
            r"\dM\d+(?:[^A-Z0-9]|$)",
            name,
        )
    )

    if is_lifestyle:
        group = 90

    elif (
        "FRONT" in name
        or re.search(
            r"(?:^|[_\s.-])A(?:\d+)?(?:[_\s.-]|$)",
            name,
        )
    ):
        group = 10

    elif "OPEN" in name:
        group = 20

    elif (
        "LEFT" in name
        or re.search(
            r"(?:^|[_\s.-])B(?:\d+)?(?:[_\s.-]|$)",
            name,
        )
    ):
        group = 30

    elif (
        "RIGHT" in name
        or re.search(
            r"(?:^|[_\s.-])C(?:\d+)?(?:[_\s.-]|$)",
            name,
        )
    ):
        group = 40

    elif (
        "BACK" in name
        or re.search(
            r"(?:^|[_\s.-])D(?:\d+)?(?:[_\s.-]|$)",
            name,
        )
    ):
        group = 50

    elif any(
        marker in name
        for marker in (
            "DETAIL",
            "CLOSE",
            "CLOSEUP",
            "ZOOM",
        )
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
    """
    Izņem Brandfolder attēlu dublikātus.

    Ja vairākiem attēliem ir vienāda normalizētā atslēga,
    tiek saglabāts attēls ar augstāko prioritāti.
    """
    unique: dict[
        str,
        dict[str, Any],
    ] = {}

    for image in images:
        key = image_key(image)

        if not key:
            continue

        current = unique.get(key)

        if current is None:
            unique[key] = image
            continue

        if image_priority(image) < image_priority(current):
            unique[key] = image

    result = list(
        unique.values()
    )

    result.sort(
        key=image_priority
    )

    return result


def existing_woocommerce_keys(
    images: list[dict[str, Any]],
) -> set[str]:
    """
    Izveido esošo WooCommerce attēlu atslēgu kopu.

    Salīdzināšanai izmanto:
      - name;
      - alt;
      - src adreses faila nosaukumu.
    """
    keys: set[str] = set()

    for image in images:
        if not isinstance(
            image,
            dict,
        ):
            continue

        candidates = [
            image.get("name"),
            image.get("alt"),
            filename_from_url(
                image.get("src")
            ),
        ]

        for candidate in candidates:
            key = normalize_filename(
                candidate
            )

            if key:
                keys.add(key)

    return keys


def prepare_image_update(
    product: dict[str, Any],
    raw_brandfolder_images: list[dict[str, Any]],
    *,
    max_images_per_product: int | None = None,
) -> dict[str, Any]:
    """
    Sagatavo attēlu sinhronizācijas plānu.

    Noteikumi:
      - esošie WooCommerce attēli netiek dzēsti;
      - esošā secība un galvenais attēls tiek saglabāti;
      - Brandfolder attēli tiek prioritizēti;
      - netiek pievienots vairāk attēlu par galerijas limitu;
      - ja galerijas limits jau sasniegts, jauni attēli
        netiek pievienoti.

    max_images_per_product parametrs galvenokārt paredzēts
    izolētiem testiem. Ja tas nav norādīts, tiek izmantota
    centralizētās konfigurācijas vērtība.
    """
    image_limit = (
        MAX_IMAGES_PER_PRODUCT
        if max_images_per_product is None
        else max_images_per_product
    )

    if image_limit < 1:
        raise ValueError(
            "max_images_per_product jābūt vismaz 1."
        )

    existing_raw = product.get(
        "images",
        [],
    )

    existing_images = (
        existing_raw
        if isinstance(
            existing_raw,
            list,
        )
        else []
    )

    brandfolder_images = (
        deduplicate_brandfolder_images(
            raw_brandfolder_images
        )
    )

    woo_keys = existing_woocommerce_keys(
        existing_images
    )

    already_present: list[
        dict[str, Any]
    ] = []

    all_missing_images: list[
        dict[str, Any]
    ] = []

    for image in brandfolder_images:
        key = image_key(image)

        if not key:
            continue

        if key in woo_keys:
            already_present.append(
                image
            )
        else:
            all_missing_images.append(
                image
            )

    available_slots = max(
        0,
        image_limit - len(existing_images),
    )

    missing_images = (
        all_missing_images[
            :available_slots
        ]
    )

    skipped_due_to_limit = (
        all_missing_images[
            available_slots:
        ]
    )

    payload_images: list[
        dict[str, Any]
    ] = []

    # Esošos WooCommerce attēlus saglabājam
    # tādā pašā secībā.
    for image in existing_images:
        if not isinstance(
            image,
            dict,
        ):
            continue

        image_id = image.get("id")

        if image_id:
            payload_images.append(
                {
                    "id": int(image_id),
                }
            )

    # Jaunos Brandfolder attēlus pievienojam
    # prioritārā secībā līdz galerijas limitam.
    for image in missing_images:
        filename = str(
            image.get("filename")
            or image.get("name")
            or filename_from_url(
                image.get("url")
                or image.get("src")
            )
            or ""
        ).strip()

        url = str(
            image.get("url")
            or image.get("src")
            or ""
        ).strip()

        if not url:
            continue

        payload_images.append(
            {
                "src": url,
                "name": filename,
                "alt": (
                    Path(filename).stem
                    if filename
                    else ""
                ),
            }
        )

    return {
        "max_images": image_limit,
        "available_slots": available_slots,
        "existing_images": existing_images,
        "brandfolder_images": brandfolder_images,
        "already_present": already_present,
        "all_missing_images": all_missing_images,
        "missing_images": missing_images,
        "skipped_due_to_limit": skipped_due_to_limit,
        "payload_images": payload_images,
    }
