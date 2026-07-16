#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests
from dotenv import load_dotenv

from src.brandfolder import create_session as create_brandfolder_session
from src.brandfolder import get_product_images
from src.woocommerce import load_products


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

WC_URL = os.getenv("WC_URL", "").rstrip("/")
WC_CONSUMER_KEY = os.getenv("WC_CONSUMER_KEY")
WC_CONSUMER_SECRET = os.getenv("WC_CONSUMER_SECRET")


class ImageSyncError(RuntimeError):
    """WooCommerce attēlu sinhronizācijas kļūda."""


def normalize_sku(value: Any) -> str:
    return str(value or "").strip().upper()


def filename_from_url(url: Any) -> str:
    text = str(url or "").strip()

    if not text:
        return ""

    parsed = urlparse(text)
    return Path(unquote(parsed.path)).name


def normalize_filename(value: Any) -> str:
    """
    Izveido faila salīdzināšanas atslēgu.

    Piemēram:
      7032A1_rgb.png
      7032A1_rgb-1.png
      7032A1_rgb-scaled.png

    tiek uzskatīti par vienu attēlu.
    """
    text = unquote(str(value or "")).strip()

    if not text:
        return ""

    text = text.split("?", 1)[0]
    text = text.split("#", 1)[0]
    text = Path(text).name

    stem = Path(text).stem.upper()

    # Vispirms noņemam WordPress -scaled.
    stem = re.sub(r"-SCALED$", "", stem)

    # Tad WordPress dublikātu sufiksus -1, -2 utt.
    stem = re.sub(r"-\d+$", "", stem)

    # Ignorējam atstarpju, domuzīmju un _ atšķirības.
    stem = re.sub(r"[\s_-]+", "", stem)

    return stem


def image_key(image: dict[str, Any]) -> str:
    return normalize_filename(
        image.get("filename")
        or image.get("name")
        or filename_from_url(
            image.get("src") or image.get("url")
        )
    )


def deduplicate_brandfolder_images(
    images: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Vienā Brandfolder meklējumā viens fails var parādīties
    vairākos aktīvos. Atstājam tikai vienu attēlu katram
    normalizētajam faila nosaukumam.
    """
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
        key=lambda image: (
            str(image.get("filename") or "").upper()
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

    woo_keys = existing_woocommerce_keys(existing_images)

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

    # Saglabājam esošos WooCommerce Media Library attēlus.
    # Pirmais paliek galvenais produkta attēls.
    for image in existing_images:
        if not isinstance(image, dict):
            continue

        image_id = image.get("id")

        if image_id:
            payload_images.append({"id": int(image_id)})

    # Pievienojam tikai patiesi trūkstošos attēlus.
    for image in missing_images:
        filename = str(image.get("filename") or "").strip()
        url = str(image.get("url") or "").strip()

        if not url:
            continue

        payload_images.append(
            {
                "src": url,
                "name": filename,
                "alt": Path(filename).stem if filename else "",
            }
        )

    return {
        "existing_images": existing_images,
        "brandfolder_images": brandfolder_images,
        "already_present": already_present,
        "missing_images": missing_images,
        "payload_images": payload_images,
    }


def update_product_images(
    product_id: int,
    payload_images: list[dict[str, Any]],
) -> dict[str, Any]:
    if not WC_URL:
        raise ImageSyncError(
            "WC_URL nav norādīts .env failā."
        )

    if not WC_CONSUMER_KEY or not WC_CONSUMER_SECRET:
        raise ImageSyncError(
            "WooCommerce API atslēgas nav norādītas .env failā."
        )

    response = requests.put(
        f"{WC_URL}/wp-json/wc/v3/products/{product_id}",
        auth=(
            WC_CONSUMER_KEY,
            WC_CONSUMER_SECRET,
        ),
        json={"images": payload_images},
        timeout=(30, 600),
    )

    if not response.ok:
        print("\nWooCommerce atbilde:")
        print(response.text[:2000])

    response.raise_for_status()

    payload = response.json()

    if not isinstance(payload, dict):
        raise ImageSyncError(
            "WooCommerce atgrieza negaidītu datu formātu."
        )

    return payload


def display_filename(image: dict[str, Any]) -> str:
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

    for number, image in enumerate(images, start=1):
        print(f"  {number}. {display_filename(image)}")


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
        print("\nBrandfolder produktu attēli netika atrasti.")
        return False

    if not plan["missing_images"]:
        print(
            "\n✅ Visi unikālie Brandfolder attēli jau ir WooCommerce."
        )
        print("Nekādas izmaiņas nav nepieciešamas.")
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
        print("\nDRY RUN — WooCommerce nekas netika mainīts.")
        print(
            "\nReālai sinhronizācijai palaid:\n"
            f"python3 -m src.image_sync "
            f"{normalized_sku} --apply"
        )
        return False

    print("\nPievieno tikai trūkstošos attēlus...")

    updated_product = update_product_images(
        product_id=int(product["id"]),
        payload_images=plan["payload_images"],
    )

    updated_images = updated_product.get("images", [])

    print("\n✅ Attēlu sinhronizācija pabeigta.")
    print(
        "WooCommerce attēlu skaits pēc atjaunināšanas: "
        f"{len(updated_images) if isinstance(updated_images, list) else 0}"
    )

    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Pievieno tikai trūkstošos Brandfolder attēlus "
            "WooCommerce produktam."
        )
    )

    parser.add_argument(
        "sku",
        help="WooCommerce produkta SKU, piemēram, 7032.",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Reāli veikt izmaiņas WooCommerce.",
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