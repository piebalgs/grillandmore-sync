#!/usr/bin/env python3

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

from src.image_processor import (
    describe_processed_image,
    process_remote_image,
)
from src.media.media_index import (
    build_media_index,
    find_media_id,
    normalize_filename,
)
from src.media.planner import filename_from_url


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

WC_URL = os.getenv("WC_URL", "").rstrip("/")
WC_CONSUMER_KEY = os.getenv("WC_CONSUMER_KEY")
WC_CONSUMER_SECRET = os.getenv("WC_CONSUMER_SECRET")

WP_USERNAME = os.getenv("WP_USERNAME", "").strip()
WP_APP_PASSWORD = "".join(
    os.getenv("WP_APP_PASSWORD", "").split()
)

RETRY_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504,
}

RETRY_DELAYS = (
    20,
    45,
    90,
)

PRODUCT_UPDATE_PAUSE = 3

# Media Library indekss tiek izveidots tikai vienu reizi viena
# Python procesa laikā. Ja sinhronizē vairākus produktus, visiem
# produktiem tiek izmantots tas pats atjaunināmais indekss.
_MEDIA_INDEX_CACHE: dict[str, int] | None = None

# Vienam WooCommerce produktam kopā atļaujam maksimums 10 attēlus.
# Vajadzības gadījumā .env failā vari norādīt citu vērtību:
# MAX_IMAGES_PER_PRODUCT=10
MAX_IMAGES_PER_PRODUCT = max(
    1,
    int(os.getenv("MAX_IMAGES_PER_PRODUCT", "10")),
)


class ImageSyncError(RuntimeError):
    """WooCommerce vai WordPress attēlu sinhronizācijas kļūda."""


def validate_configuration() -> None:
    missing: list[str] = []

    if not WC_URL:
        missing.append("WC_URL")

    if not WC_CONSUMER_KEY:
        missing.append("WC_CONSUMER_KEY")

    if not WC_CONSUMER_SECRET:
        missing.append("WC_CONSUMER_SECRET")

    if not WP_USERNAME:
        missing.append("WP_USERNAME")

    if not WP_APP_PASSWORD:
        missing.append("WP_APP_PASSWORD")

    if missing:
        raise ImageSyncError(
            ".env failā trūkst: "
            + ", ".join(missing)
        )


def wordpress_auth() -> tuple[str, str]:
    if not WP_USERNAME or not WP_APP_PASSWORD:
        raise ImageSyncError(
            "WordPress Media API piekļuves dati nav norādīti."
        )

    return WP_USERNAME, WP_APP_PASSWORD


def wc_auth() -> tuple[str, str]:
    if not WC_CONSUMER_KEY or not WC_CONSUMER_SECRET:
        raise ImageSyncError(
            "WooCommerce API piekļuves dati nav norādīti."
        )

    return WC_CONSUMER_KEY, WC_CONSUMER_SECRET


def request_with_retry(
    *,
    method: str,
    url: str,
    request_name: str,
    acceptable_statuses: set[int] | None = None,
    **kwargs: Any,
) -> requests.Response:
    last_error: Exception | None = None

    acceptable = acceptable_statuses or {
        200,
        201,
    }

    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            response = requests.request(
                method,
                url,
                **kwargs,
            )

            if response.status_code in acceptable:
                return response

            if response.status_code not in RETRY_STATUS_CODES:
                print("\nServera atbilde:")
                print(response.text[:2000])
                response.raise_for_status()

            last_error = requests.HTTPError(
                (
                    f"{request_name}: "
                    f"HTTP {response.status_code}"
                ),
                response=response,
            )

        except requests.HTTPError as error:
            status_code = (
                error.response.status_code
                if error.response is not None
                else None
            )

            # 400, 401, 403, 404 u.c. pastāvīgas kļūdas
            # netiek atkārtotas.
            if status_code not in RETRY_STATUS_CODES:
                raise

            last_error = error

        except requests.RequestException as error:
            last_error = error

        if attempt >= len(RETRY_DELAYS):
            break

        delay = RETRY_DELAYS[attempt]

        print(
            f"    ⚠ {request_name} neizdevās. "
            f"Mēģinājums {attempt + 2} no "
            f"{len(RETRY_DELAYS) + 1} pēc "
            f"{delay} sekundēm..."
        )

        time.sleep(delay)

    raise ImageSyncError(
        f"{request_name} neizdevās pēc "
        f"{len(RETRY_DELAYS) + 1} mēģinājumiem. "
        f"Pēdējā kļūda: {last_error}"
    )


def upload_media_file(
    *,
    file_path: Path,
    filename: str,
    content_type: str,
    alt_text: str,
) -> dict[str, Any]:
    endpoint = (
        f"{WC_URL}/wp-json/wp/v2/media"
    )

    file_bytes = file_path.read_bytes()

    response = request_with_retry(
        method="POST",
        url=endpoint,
        request_name=f"Media augšupielāde {filename}",
        acceptable_statuses={201},
        auth=wordpress_auth(),
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            ),
            "Content-Type": content_type,
            "Accept": "application/json",
        },
        data=file_bytes,
        timeout=(30, 300),
    )

    media = response.json()

    if not isinstance(media, dict):
        raise ImageSyncError(
            "WordPress Media API atgrieza "
            "negaidītu datu formātu."
        )

    media_id = media.get("id")

    if not media_id:
        raise ImageSyncError(
            f"WordPress neizveidoja Media ID failam {filename}."
        )

    metadata_endpoint = (
        f"{WC_URL}/wp-json/wp/v2/media/{media_id}"
    )

    metadata_response = request_with_retry(
        method="POST",
        url=metadata_endpoint,
        request_name=f"Media metadati {filename}",
        acceptable_statuses={200},
        auth=wordpress_auth(),
        json={
            "title": Path(filename).stem,
            "alt_text": alt_text,
            "caption": "",
            "description": "",
        },
        timeout=(30, 120),
    )

    metadata = metadata_response.json()

    if isinstance(metadata, dict):
        media.update(metadata)

    return media


def verify_media_exists(
    media_id: int,
) -> dict[str, Any]:
    endpoint = (
        f"{WC_URL}/wp-json/wp/v2/media/"
        f"{media_id}?context=edit"
    )

    response = requests.get(
        endpoint,
        auth=wordpress_auth(),
        timeout=(30, 120),
    )

    if response.status_code == 404:
        raise ImageSyncError(
            f"WordPress Media ID {media_id} "
            "pēc augšupielādes vairs neeksistē."
        )

    response.raise_for_status()
    payload = response.json()

    if not isinstance(payload, dict):
        raise ImageSyncError(
            f"Media ID {media_id} atgrieza "
            "negaidītu datu formātu."
        )

    if payload.get("media_type") != "image":
        raise ImageSyncError(
            f"Media ID {media_id} nav attēls."
        )

    return payload


def put_product_image_ids(
    *,
    product_id: int,
    image_ids: list[int],
) -> dict[str, Any]:
    endpoint = (
        f"{WC_URL}/wp-json/wc/v3/products/{product_id}"
    )

    response = request_with_retry(
        method="PUT",
        url=endpoint,
        request_name=f"WooCommerce produkts {product_id}",
        acceptable_statuses={200},
        auth=wc_auth(),
        json={
            "images": [
                {
                    "id": image_id,
                }
                for image_id in image_ids
            ]
        },
        timeout=(30, 300),
    )

    payload = response.json()

    if not isinstance(payload, dict):
        raise ImageSyncError(
            "WooCommerce atgrieza negaidītu datu formātu."
        )

    return payload



def get_media_index(
    *,
    force_refresh: bool = False,
    verbose: bool = True,
) -> dict[str, int]:
    """
    Atgriež WordPress Media Library indeksu.

    Indekss tiek izveidots tikai vienu reizi viena Python procesa
    laikā. force_refresh=True piespiedu kārtā nolasa Media Library
    no jauna.
    """
    global _MEDIA_INDEX_CACHE

    if _MEDIA_INDEX_CACHE is None or force_refresh:
        _MEDIA_INDEX_CACHE = build_media_index(
            verbose=verbose,
        )

    return _MEDIA_INDEX_CACHE


def clear_media_index_cache() -> None:
    """Notīra šī Python procesa Media Library indeksa kešatmiņu."""
    global _MEDIA_INDEX_CACHE
    _MEDIA_INDEX_CACHE = None


def resolve_media_id(
    *,
    processed: Any,
    alt_text: str,
    media_index: dict[str, int],
) -> int:
    """
    Atrod esošu Media ID vai augšupielādē jaunu attēlu.

    Darbības:
      1. meklē failu Media Library indeksā;
      2. ja atrod, izmanto esošo Media ID;
      3. ja neatrod, augšupielādē failu;
      4. pārbauda jaunā Media ID eksistenci;
      5. uzreiz papildina indeksu.
    """
    filename = str(processed.filename or "").strip()

    if not filename:
        raise ImageSyncError(
            "Apstrādātajam attēlam nav faila nosaukuma."
        )

    existing_media_id = find_media_id(
        media_index,
        filename,
    )

    if existing_media_id is not None:
        print(
            f"    ✓ Izmantots esošs Media Library ID: "
            f"{existing_media_id}"
        )
        return int(existing_media_id)

    media = upload_media_file(
        file_path=processed.path,
        filename=filename,
        content_type=processed.content_type,
        alt_text=alt_text,
    )

    media_id = int(media["id"])
    verify_media_exists(media_id)

    index_key = normalize_filename(filename)

    if not index_key:
        raise ImageSyncError(
            f"Neizdevās normalizēt faila nosaukumu {filename}."
        )

    media_index[index_key] = media_id

    print(
        f"    ✓ Augšupielādēts jauns Media Library ID: "
        f"{media_id}"
    )

    return media_id

def update_product_images(
    product_id: int,
    payload_images: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Saglabā esošos Media ID un katru jauno attēlu:

      1. lejupielādē Python pusē;
      2. pārveido uz 800×800;
      3. augšupielādē WordPress Media Library;
      4. pārbauda Media ID;
      5. uzreiz piesaista WooCommerce produktam.

    Stingrais limits tiek pārbaudīts arī šajā līmenī,
    tāpēc fiziski nevar augšupielādēt vairāk par brīvajām
    vietām līdz MAX_IMAGES_PER_PRODUCT.
    """
    validate_configuration()

    existing_ids: list[int] = []
    remote_images: list[dict[str, Any]] = []

    for item in payload_images:
        image_id = item.get("id")

        if image_id:
            existing_ids.append(int(image_id))
            continue

        source_url = str(
            item.get("src") or ""
        ).strip()

        if source_url:
            remote_images.append(item)

    current_ids = list(dict.fromkeys(existing_ids))

    available_slots = max(
        0,
        MAX_IMAGES_PER_PRODUCT - len(current_ids),
    )

    skipped_count = max(
        0,
        len(remote_images) - available_slots,
    )

    remote_images = remote_images[:available_slots]

    print(
        f"  Esošie WooCommerce attēli: {len(current_ids)}"
    )
    print(
        f"  Brīvās vietas līdz limitam: {available_slots}"
    )

    if skipped_count:
        print(
            f"  ⚠ Limita dēļ netiks augšupielādēti "
            f"{skipped_count} attēli."
        )

    if not remote_images:
        print(
            "  Attēlu limits sasniegts vai nav jaunu attēlu."
        )

        # Ja ir esoši attēli, atstājam tos nemainītus.
        # Produktam ar vairāk nekā 10 esošiem attēliem
        # neko automātiski nedzēšam.
        return put_product_image_ids(
            product_id=product_id,
            image_ids=current_ids,
        )

    media_index = get_media_index(
        verbose=True,
    )

    download_session = requests.Session()
    download_session.headers.update(
        {
            "User-Agent": (
                "GrillAndMore-Sync/0.4 "
                "(image processor)"
            ),
            "Accept": "image/*,*/*;q=0.8",
        }
    )

    last_product: dict[str, Any] | None = None

    try:
        for number, image in enumerate(
            remote_images,
            start=1,
        ):
            source_url = str(
                image.get("src") or ""
            ).strip()

            original_filename = str(
                image.get("name")
                or filename_from_url(source_url)
                or "product-image"
            ).strip()

            alt_text = str(
                image.get("alt")
                or Path(original_filename).stem
            ).strip()

            print(
                f"\n  [{number}/{len(remote_images)}] "
                f"{original_filename}"
            )

            processed = process_remote_image(
                url=source_url,
                filename=original_filename,
                session=download_session,
                use_cache=True,
            )

            print(
                "    "
                + describe_processed_image(processed)
            )

            media_id = resolve_media_id(
                processed=processed,
                alt_text=alt_text,
                media_index=media_index,
            )

            if media_id not in current_ids:
                current_ids.append(media_id)

            # Papildu drošība: nekad nepārsniedzam limitu
            # ar jaunajiem attēliem.
            if len(existing_ids) < MAX_IMAGES_PER_PRODUCT:
                current_ids = current_ids[:MAX_IMAGES_PER_PRODUCT]

            last_product = put_product_image_ids(
                product_id=product_id,
                image_ids=current_ids,
            )

            print(
                "    ✓ Pievienots WooCommerce produktam."
            )

            time.sleep(PRODUCT_UPDATE_PAUSE)

    finally:
        download_session.close()

    if last_product is None:
        last_product = put_product_image_ids(
            product_id=product_id,
            image_ids=current_ids,
        )

    return last_product

