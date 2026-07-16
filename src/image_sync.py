#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests
from dotenv import load_dotenv

from src.brandfolder import (
    create_session as create_brandfolder_session,
)
from src.brandfolder import get_product_images
from src.image_processor import (
    ImageProcessingError,
    describe_processed_image,
    process_remote_image,
)
from src.woocommerce import load_products


PROJECT_ROOT = Path(__file__).resolve().parent.parent
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


class ImageSyncError(RuntimeError):
    """WooCommerce vai WordPress attēlu sinhronizācijas kļūda."""


def normalize_sku(value: Any) -> str:
    return str(value or "").strip().upper()


def filename_from_url(url: Any) -> str:
    text = str(url or "").strip()

    if not text:
        return ""

    parsed = urlparse(text)
    return Path(unquote(parsed.path)).name


def normalize_filename(value: Any) -> str:
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
    return normalize_filename(
        image.get("filename")
        or image.get("name")
        or filename_from_url(
            image.get("src")
            or image.get("url")
        )
    )


def deduplicate_brandfolder_images(
    images: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}

    for image in images:
        key = image_key(image)

        if not key:
            continue

        current = unique.get(key)

        if current is None:
            unique[key] = image
            continue

        try:
            current_position = int(
                current.get("position", 9999)
            )
        except (TypeError, ValueError):
            current_position = 9999

        try:
            new_position = int(
                image.get("position", 9999)
            )
        except (TypeError, ValueError):
            new_position = 9999

        if new_position < current_position:
            unique[key] = image

    result = list(unique.values())

    result.sort(
        key=lambda item: (
            int(item.get("position", 9999)),
            str(item.get("filename") or "").upper(),
        )
    )

    return result


def existing_woocommerce_keys(
    images: list[dict[str, Any]],
) -> set[str]:
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


def find_product_by_sku(
    products: list[dict[str, Any]],
    sku: str,
) -> dict[str, Any] | None:
    wanted = normalize_sku(sku)

    for product in products:
        if normalize_sku(product.get("sku")) == wanted:
            return product

    return None


def prepare_image_update(
    product: dict[str, Any],
    raw_brandfolder_images: list[dict[str, Any]],
) -> dict[str, Any]:
    existing_raw = product.get("images", [])

    existing_images = (
        existing_raw
        if isinstance(existing_raw, list)
        else []
    )

    brandfolder_images = deduplicate_brandfolder_images(
        raw_brandfolder_images
    )

    woo_keys = existing_woocommerce_keys(
        existing_images
    )

    already_present: list[dict[str, Any]] = []
    missing_images: list[dict[str, Any]] = []

    for image in brandfolder_images:
        key = image_key(image)

        if not key:
            continue

        if key in woo_keys:
            already_present.append(image)
        else:
            missing_images.append(image)

    payload_images: list[dict[str, Any]] = []

    for image in existing_images:
        if not isinstance(image, dict):
            continue

        image_id = image.get("id")

        if image_id:
            payload_images.append(
                {
                    "id": int(image_id),
                }
            )

    for image in missing_images:
        filename = str(
            image.get("filename") or ""
        ).strip()

        url = str(
            image.get("url") or ""
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
        "existing_images": existing_images,
        "brandfolder_images": brandfolder_images,
        "already_present": already_present,
        "missing_images": missing_images,
        "payload_images": payload_images,
    }


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


def update_product_images(
    product_id: int,
    payload_images: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Saglabā esošos Media ID un katru jauno attēlu:

      1. lejupielādē Python pusē;
      2. pārveido uz 800×800;
      3. augšupielādē WordPress Media Library;
      4. uzreiz piesaista WooCommerce produktam.

    Produkts tiek saglabāts pēc katra attēla, tādēļ,
    ja process pārtrūkst, veiksmīgi pievienotie attēli
    nepazūd un nākamajā palaišanā netiek dublēti.
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

    if not remote_images:
        return put_product_image_ids(
            product_id=product_id,
            image_ids=current_ids,
        )

    download_session = requests.Session()
    download_session.headers.update(
        {
            "User-Agent": (
                "GrillAndMore-Sync/0.3 "
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

            media = upload_media_file(
                file_path=processed.path,
                filename=processed.filename,
                content_type=processed.content_type,
                alt_text=alt_text,
            )

            media_id = int(media["id"])

            if media_id not in current_ids:
                current_ids.append(media_id)

            print(
                f"    ✓ Media Library ID: {media_id}"
            )

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


def display_filename(
    image: dict[str, Any],
) -> str:
    return str(
        image.get("filename")
        or image.get("name")
        or filename_from_url(image.get("src"))
        or ""
    )


def print_image_list(
    title: str,
    images: list[dict[str, Any]],
) -> None:
    print(f"\n{title}: {len(images)}")

    for number, image in enumerate(
        images,
        start=1,
    ):
        print(
            f"  {number}. {display_filename(image)}"
        )


def sync_one_product(
    sku: str,
    *,
    apply: bool = False,
    use_cache: bool = False,
) -> bool:
    normalized_sku = normalize_sku(sku)

    products = load_products()

    product = find_product_by_sku(
        products,
        normalized_sku,
    )

    if not product:
        print(
            f"SKU {normalized_sku} WooCommerce netika atrasts."
        )
        return False

    with create_brandfolder_session() as session:
        raw_brandfolder_images = get_product_images(
            normalized_sku,
            use_cache=use_cache,
            session=session,
        )

    plan = prepare_image_update(
        product=product,
        raw_brandfolder_images=raw_brandfolder_images,
    )

    print("\n" + "=" * 70)
    print("BRANDFOLDER → WOOCOMMERCE ATTĒLU SINHRONIZĀCIJA")
    print("=" * 70)
    print(f"SKU:                         {normalized_sku}")
    print(f"Produkts:                    {product.get('name', '')}")
    print(f"WooCommerce ID:              {product.get('id')}")
    print(
        "Brandfolder sākotnējie ieraksti: "
        f"{len(raw_brandfolder_images)}"
    )
    print(
        "Brandfolder unikālie attēli:     "
        f"{len(plan['brandfolder_images'])}"
    )

    print_image_list(
        "WooCommerce pašreizējie attēli",
        plan["existing_images"],
    )

    print_image_list(
        "Brandfolder attēli, kuri jau ir WooCommerce",
        plan["already_present"],
    )

    print_image_list(
        "Trūkstošie attēli, kuri tiks pievienoti",
        plan["missing_images"],
    )

    if not plan["brandfolder_images"]:
        print(
            "\nBrandfolder produktu attēli netika atrasti."
        )
        return False

    if not plan["missing_images"]:
        print(
            "\n✅ Visi Brandfolder attēli jau ir WooCommerce."
        )
        return False

    print(
        "\nPēc sinhronizācijas kopējais attēlu skaits būs: "
        f"{len(plan['payload_images'])}"
    )

    if plan["existing_images"]:
        print(
            "Galvenais produkta attēls tiks saglabāts: "
            f"{display_filename(plan['existing_images'][0])}"
        )
    else:
        print(
            "Produktam nav esoša galvenā attēla. "
            "Pirmais Brandfolder attēls kļūs par galveno."
        )

    if not apply:
        print(
            "\nDRY RUN — WooCommerce nekas netika mainīts."
        )
        return False

    product_id = product.get("id")

    if not product_id:
        raise ImageSyncError(
            "WooCommerce produktam nav ID."
        )

    print(
        "\nLejupielādē, samazina un augšupielādē "
        "trūkstošos attēlus..."
    )

    updated_product = update_product_images(
        product_id=int(product_id),
        payload_images=plan["payload_images"],
    )

    updated_images = updated_product.get(
        "images",
        [],
    )

    print("\n✅ Attēlu sinhronizācija pabeigta.")
    print(
        "WooCommerce attēlu skaits: "
        f"{len(updated_images) if isinstance(updated_images, list) else 0}"
    )

    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Samazina Brandfolder attēlus līdz 800×800 "
            "un augšupielādē WordPress Media Library."
        )
    )

    parser.add_argument(
        "sku",
        help="WooCommerce produkta SKU.",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Reāli veikt izmaiņas.",
    )

    parser.add_argument(
        "--cache",
        action="store_true",
        help="Izmantot Brandfolder kešatmiņu.",
    )

    args = parser.parse_args()

    sync_one_product(
        args.sku,
        apply=args.apply,
        use_cache=args.cache,
    )


if __name__ == "__main__":
    main()