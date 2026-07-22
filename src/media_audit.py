#!/usr/bin/env python3

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests

from src.brandfolder import get_product_images
from src.image_utils import (
    deduplicate_brandfolder_images,
    existing_woocommerce_keys,
    filename_from_url,
    image_key,
    normalize_filename,
    normalize_sku,
)


MAX_IMAGES_PER_PRODUCT = 10
LEGACY_EXTENSIONS = {".jpg", ".jpeg", ".png"}
WEBP_EXTENSION = ".webp"


@dataclass(slots=True)
class MediaAuditResult:
    catalogue_position: int
    product_id: int | None
    sku: str
    product: str
    brand: str
    wc_images: int
    bf_images: int | None
    expected_images: int | None
    webp_images: int
    legacy_images: int
    other_images: int
    missing_media_ids: int
    duplicate_media_ids: int
    duplicate_filenames: int
    missing_from_wc: int | None
    extra_in_wc: int | None
    over_limit: int
    status: str
    severity: str
    health: int
    notes: str
    brandfolder_error: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_text(value: Any) -> str:
    return str(value or "").strip().casefold()


def product_brand_name(product: dict[str, Any]) -> str:
    brands = product.get("brands", [])

    if not isinstance(brands, list):
        return ""

    names: list[str] = []

    for brand in brands:
        if not isinstance(brand, dict):
            continue

        name = str(
            brand.get("name")
            or brand.get("slug")
            or ""
        ).strip()

        if name and name not in names:
            names.append(name)

    return ", ".join(names)


def product_has_brand(
    product: dict[str, Any],
    requested_brand: str,
) -> bool:
    wanted = normalize_text(requested_brand)

    if not wanted:
        return True

    searchable_values: list[str] = [
        str(product.get("name") or ""),
        str(product.get("brand") or ""),
        str(product.get("producer") or ""),
    ]

    for key in ("brands", "categories", "tags", "attributes"):
        values = product.get(key, [])

        if not isinstance(values, list):
            continue

        for item in values:
            if not isinstance(item, dict):
                continue

            searchable_values.extend(
                [
                    str(item.get("name") or ""),
                    str(item.get("option") or ""),
                    str(item.get("slug") or ""),
                ]
            )

            options = item.get("options", [])

            if isinstance(options, list):
                searchable_values.extend(
                    str(option)
                    for option in options
                )

    searchable_text = " ".join(searchable_values).casefold()
    return wanted in searchable_text


def filter_products(
    products: list[dict[str, Any]],
    *,
    brand: str | None,
    exclude_brand: str | None = None,
    sku_filter: set[str] | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []

    for product in products:
        if not isinstance(product, dict):
            continue

        sku = normalize_sku(product.get("sku"))

        if not sku:
            continue

        if brand and not product_has_brand(product, brand):
            continue

        if exclude_brand and product_has_brand(product, exclude_brand):
            continue

        if sku_filter is not None and sku not in sku_filter:
            continue

        selected.append(product)

    return selected


def select_product_range(
    products: list[dict[str, Any]],
    *,
    offset: int,
    limit: int | None,
) -> list[dict[str, Any]]:
    if limit is None:
        return products[offset:]

    return products[offset:offset + limit]


def wc_images(product: dict[str, Any]) -> list[dict[str, Any]]:
    images = product.get("images", [])

    if not isinstance(images, list):
        return []

    return [
        image
        for image in images
        if isinstance(image, dict)
    ]


def wc_image_filename(image: dict[str, Any]) -> str:
    return (
        filename_from_url(image.get("src"))
        or str(image.get("name") or "").strip()
        or str(image.get("alt") or "").strip()
    )


def wc_image_extension(image: dict[str, Any]) -> str:
    return Path(wc_image_filename(image)).suffix.lower()


def count_formats(
    images: list[dict[str, Any]],
) -> tuple[int, int, int]:
    webp = 0
    legacy = 0
    other = 0

    for image in images:
        extension = wc_image_extension(image)

        if extension == WEBP_EXTENSION:
            webp += 1
        elif extension in LEGACY_EXTENSIONS:
            legacy += 1
        else:
            other += 1

    return webp, legacy, other


def count_missing_media_ids(
    images: list[dict[str, Any]],
) -> int:
    missing = 0

    for image in images:
        image_id = image.get("id")

        try:
            parsed = int(image_id)
        except (TypeError, ValueError):
            missing += 1
            continue

        if parsed <= 0:
            missing += 1

    return missing


def count_duplicate_media_ids(
    images: list[dict[str, Any]],
) -> int:
    ids: list[int] = []

    for image in images:
        try:
            image_id = int(image.get("id"))
        except (TypeError, ValueError):
            continue

        if image_id > 0:
            ids.append(image_id)

    return len(ids) - len(set(ids))


def count_duplicate_filenames(
    images: list[dict[str, Any]],
) -> int:
    keys: list[str] = []

    for image in images:
        candidates = [
            image.get("name"),
            image.get("alt"),
            wc_image_filename(image),
        ]

        key = ""

        for candidate in candidates:
            key = normalize_filename(candidate)

            if key:
                break

        if key:
            keys.append(key)

    return len(keys) - len(set(keys))


def compare_image_keys(
    *,
    wc: list[dict[str, Any]],
    brandfolder: list[dict[str, Any]],
) -> tuple[int, int]:
    wc_keys = existing_woocommerce_keys(wc)

    bf_keys = {
        image_key(image)
        for image in brandfolder
        if image_key(image)
    }

    missing_from_wc = len(bf_keys - wc_keys)
    extra_in_wc = len(wc_keys - bf_keys)

    return missing_from_wc, extra_in_wc


def assess_status(
    *,
    wc_count: int,
    bf_count: int | None,
    legacy_count: int,
    other_count: int,
    missing_media_ids: int,
    duplicate_media_ids: int,
    duplicate_filenames: int,
    missing_from_wc: int | None,
    over_limit: int,
    brandfolder_error: str,
) -> tuple[str, str, int, list[str]]:
    notes: list[str] = []
    score = 100

    if brandfolder_error:
        notes.append("Brandfolder pārbaude neizdevās.")
        return "FAIL_BRANDFOLDER", "FAIL", 20, notes

    if missing_media_ids:
        notes.append(
            f"{missing_media_ids} attēliem nav derīga Media ID."
        )
        return "FAIL_MEDIA_ID", "FAIL", 20, notes

    if duplicate_media_ids or duplicate_filenames:
        if duplicate_media_ids:
            notes.append(
                f"Dublēti Media ID: {duplicate_media_ids}."
            )
        if duplicate_filenames:
            notes.append(
                f"Dublēti failu nosaukumi: {duplicate_filenames}."
            )
        return "FAIL_DUPLICATES", "FAIL", 35, notes

    if wc_count == 0 and (bf_count or 0) > 0:
        notes.append(
            f"Brandfolder ir {bf_count} attēli, bet WooCommerce galerija ir tukša."
        )
        return "FAIL_MISSING_IMAGES", "FAIL", 10, notes

    if missing_from_wc and missing_from_wc > 0:
        notes.append(
            f"WooCommerce trūkst {missing_from_wc} Brandfolder attēli."
        )
        return "FAIL_COUNT_MISMATCH", "FAIL", 45, notes

    warnings: list[str] = []

    if wc_count == 0 and (bf_count or 0) == 0:
        warnings.append(
            "Attēli nav ne WooCommerce, ne Brandfolder."
        )
        score -= 45

    if legacy_count:
        warnings.append(
            f"Galerijā vēl ir {legacy_count} PNG/JPG attēli."
        )
        score -= min(35, legacy_count * 5)

    if other_count:
        warnings.append(
            f"Galerijā ir {other_count} cita vai nenosakāma formāta attēli."
        )
        score -= min(20, other_count * 5)

    if over_limit:
        warnings.append(
            f"Galerijas limits pārsniegts par {over_limit} attēliem."
        )
        score -= min(25, over_limit * 3)

    if warnings:
        return "WARNING", "WARNING", max(0, score), warnings

    notes.append("Attēlu audits veiksmīgs.")
    return "PASS", "PASS", score, notes


def audit_product(
    *,
    product: dict[str, Any],
    catalogue_position: int,
    brandfolder_images: list[dict[str, Any]] | None,
    brandfolder_error: str = "",
    max_images: int = MAX_IMAGES_PER_PRODUCT,
) -> MediaAuditResult:
    sku = normalize_sku(product.get("sku"))
    name = str(product.get("name") or "").strip()
    product_id_raw = product.get("id")

    try:
        product_id = int(product_id_raw)
    except (TypeError, ValueError):
        product_id = None

    woo_images = wc_images(product)
    wc_count = len(woo_images)

    webp_count, legacy_count, other_count = count_formats(
        woo_images
    )

    missing_media_ids = count_missing_media_ids(
        woo_images
    )
    duplicate_media_ids = count_duplicate_media_ids(
        woo_images
    )
    duplicate_filenames = count_duplicate_filenames(
        woo_images
    )

    over_limit = max(0, wc_count - max_images)

    if brandfolder_images is None:
        bf_count = None
        expected_count = None
        missing_from_wc = None
        extra_in_wc = None
    else:
        unique_bf = deduplicate_brandfolder_images(
            brandfolder_images
        )
        bf_count = len(unique_bf)
        expected_count = min(bf_count, max_images)

        missing_from_wc, extra_in_wc = compare_image_keys(
            wc=woo_images,
            brandfolder=unique_bf[:max_images],
        )

    status, severity, health, notes = assess_status(
        wc_count=wc_count,
        bf_count=bf_count,
        legacy_count=legacy_count,
        other_count=other_count,
        missing_media_ids=missing_media_ids,
        duplicate_media_ids=duplicate_media_ids,
        duplicate_filenames=duplicate_filenames,
        missing_from_wc=missing_from_wc,
        over_limit=over_limit,
        brandfolder_error=brandfolder_error,
    )

    return MediaAuditResult(
        catalogue_position=catalogue_position,
        product_id=product_id,
        sku=sku,
        product=name,
        brand=product_brand_name(product),
        wc_images=wc_count,
        bf_images=bf_count,
        expected_images=expected_count,
        webp_images=webp_count,
        legacy_images=legacy_count,
        other_images=other_count,
        missing_media_ids=missing_media_ids,
        duplicate_media_ids=duplicate_media_ids,
        duplicate_filenames=duplicate_filenames,
        missing_from_wc=missing_from_wc,
        extra_in_wc=extra_in_wc,
        over_limit=over_limit,
        status=status,
        severity=severity,
        health=health,
        notes=" ".join(notes),
        brandfolder_error=brandfolder_error,
    )



def verify_product(
    product: dict[str, Any],
    *,
    use_cache: bool = False,
    session: requests.Session | None = None,
    max_images: int = MAX_IMAGES_PER_PRODUCT,
) -> dict[str, Any]:
    """
    Savietojamības audits, ko izmanto image_sync.py.

    Funkcija tikai nolasa un salīdzina datus. Tā neveic izmaiņas
    WooCommerce vai Brandfolder.
    """
    sku = normalize_sku(product.get("sku"))

    if not sku:
        return {
            "status": "ERROR",
            "message": "Produktam nav SKU.",
            "wc_count": len(wc_images(product)),
            "brandfolder_count": 0,
            "missing_count": 0,
            "extra_count": 0,
            "duplicate_count": 0,
            "missing_images": [],
            "extra_images": [],
        }

    own_session = session is None
    active_session = session or requests.Session()

    try:
        raw_brandfolder_images = get_product_images(
            sku,
            use_cache=use_cache,
            session=active_session,
        )
    except Exception as error:
        return {
            "status": "ERROR",
            "message": f"Brandfolder pārbaude neizdevās: {error}",
            "wc_count": len(wc_images(product)),
            "brandfolder_count": 0,
            "missing_count": 0,
            "extra_count": 0,
            "duplicate_count": 0,
            "missing_images": [],
            "extra_images": [],
        }
    finally:
        if own_session:
            active_session.close()

    woo_images = wc_images(product)
    unique_bf = deduplicate_brandfolder_images(
        raw_brandfolder_images
    )
    expected_bf = unique_bf[:max_images]

    wc_keys = existing_woocommerce_keys(woo_images)
    bf_by_key = {
        image_key(image): image
        for image in expected_bf
        if image_key(image)
    }

    bf_keys = set(bf_by_key)
    missing_keys = sorted(bf_keys - wc_keys)
    extra_keys = sorted(wc_keys - bf_keys)

    duplicate_count = (
        count_duplicate_media_ids(woo_images)
        + count_duplicate_filenames(woo_images)
    )

    missing_images = [
        str(
            bf_by_key[key].get("filename")
            or bf_by_key[key].get("name")
            or filename_from_url(
                bf_by_key[key].get("url")
                or bf_by_key[key].get("src")
            )
            or key
        )
        for key in missing_keys
    ]

    if duplicate_count:
        status = "REVIEW"
        message = "WooCommerce galerijā atrasti dublikāti."
    elif len(woo_images) > max_images:
        status = "REVIEW"
        message = (
            f"WooCommerce galerijā ir vairāk par {max_images} attēliem."
        )
    elif missing_keys:
        available_slots = max(0, max_images - len(woo_images))

        if available_slots >= len(missing_keys):
            status = "SYNC"
            message = (
                f"Jāpievieno {len(missing_keys)} Brandfolder attēli."
            )
        else:
            status = "REVIEW"
            message = (
                "Visus trūkstošos attēlus nevar pievienot "
                "galerijas limita dēļ."
            )
    else:
        status = "OK"
        message = "WooCommerce galerija atbilst Brandfolder datiem."

    return {
        "status": status,
        "message": message,
        "wc_count": len(woo_images),
        "brandfolder_count": len(unique_bf),
        "missing_count": len(missing_keys),
        "extra_count": len(extra_keys),
        "duplicate_count": duplicate_count,
        "missing_images": missing_images,
        "extra_images": extra_keys,
    }



def summarize_results(
    results: list[MediaAuditResult],
) -> Counter[str]:
    statistics: Counter[str] = Counter()

    for result in results:
        statistics["products"] += 1
        statistics[result.severity.lower()] += 1
        statistics[result.status] += 1

        if result.wc_images == 0:
            statistics["without_wc_images"] += 1

        if result.bf_images == 0:
            statistics["without_bf_images"] += 1

        if result.legacy_images:
            statistics["products_with_legacy"] += 1
            statistics["legacy_images"] += result.legacy_images

        if result.over_limit:
            statistics["products_over_limit"] += 1

        if result.duplicate_media_ids or result.duplicate_filenames:
            statistics["products_with_duplicates"] += 1

        if result.missing_media_ids:
            statistics["products_with_invalid_ids"] += 1

        if result.brandfolder_error:
            statistics["brandfolder_errors"] += 1

        if result.missing_from_wc:
            statistics["products_missing_bf_images"] += 1
            statistics["missing_bf_images"] += result.missing_from_wc

    return statistics
