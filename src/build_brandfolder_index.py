#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv

from src.woocommerce import load_products as load_woocommerce_products

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_FILE = PROJECT_ROOT / "supplier" / "brandfolder_assets.json"
OUTPUT_FILE = PROJECT_ROOT / "cache" / "brandfolder_index.json"
UNMATCHED_FILE = PROJECT_ROOT / "cache" / "brandfolder_unmatched.json"

BRANDFOLDER_API_KEY = os.getenv("BRANDFOLDER_API_KEY")
BRANDFOLDER_CDN_KEY = os.getenv(
    "BRANDFOLDER_CDN_KEY",
    "XBRZ2A26",
)

API_BASE_URL = "https://brandfolder.com/api/v4"

IMAGE_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp",
}


def api_headers() -> dict[str, str]:
    if not BRANDFOLDER_API_KEY:
        raise RuntimeError(
            "BRANDFOLDER_API_KEY nav norādīts .env failā."
        )

    return {
        "Authorization": f"Bearer {BRANDFOLDER_API_KEY}",
        "Accept": "application/json",
    }


def load_brandfolder_assets() -> list[dict[str, Any]]:
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(
            f"Fails nav atrasts: {SOURCE_FILE}"
        )

    with SOURCE_FILE.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, dict):
        raise ValueError(
            "Brandfolder JSON galvenajam elementam jābūt objektam."
        )

    data = payload.get("data", [])

    if not isinstance(data, list):
        raise ValueError(
            "Brandfolder JSON laukam 'data' jābūt sarakstam."
        )

    return data


def load_woo_skus() -> tuple[set[str], dict[str, dict[str, Any]]]:
    products = load_woocommerce_products()

    sku_index: dict[str, dict[str, Any]] = {}

    for product in products:
        sku = str(product.get("sku") or "").strip().upper()

        if sku:
            sku_index[sku] = product

    return set(sku_index), sku_index


def get_asset_attachments(
    session: requests.Session,
    asset_id: str,
) -> list[dict[str, Any]]:
    response = session.get(
        f"{API_BASE_URL}/assets/{asset_id}/attachments",
        params={
            "fields": (
                "filename,"
                "original_filename,"
                "extension,"
                "position,"
                "url,"
                "thumbnail_url"
            )
        },
        timeout=90,
    )

    if not response.ok:
        print(
            f"  ❌ Asset {asset_id}: "
            f"HTTP {response.status_code}"
        )
        print(response.text[:500])
        return []

    payload = response.json()
    data = payload.get("data", [])

    return data if isinstance(data, list) else []


def normalize_filename(filename: str) -> str:
    return filename.strip().upper()


def sku_matches_filename(sku: str, filename: str) -> bool:
    """
    SKU drīkst būt faila nosaukuma sākumā vai atsevišķs tokens.

    Piemēri:
      7032A1_rgb.png       -> 7032
      1121004_G1.jpg       -> 1121004
      product-6201-main    -> 6201
    """
    normalized = normalize_filename(filename)
    escaped_sku = re.escape(sku)

    patterns = [
        rf"^{escaped_sku}(?!\d)",
        rf"(?<![A-Z0-9]){escaped_sku}(?![A-Z0-9])",
    ]

    return any(
        re.search(pattern, normalized) is not None
        for pattern in patterns
    )


def detect_sku(
    filename: str,
    woo_skus_sorted: list[str],
) -> str | None:
    # Garākos SKU pārbaudām pirmos, lai, piemēram,
    # 1501032 netiktu sajaukts ar 1501.
    for sku in woo_skus_sorted:
        if sku_matches_filename(sku, filename):
            return sku

    return None


def make_cdn_url(
    attachment_id: str,
    filename: str,
) -> str:
    encoded_filename = quote(filename)

    return (
        f"https://cdn.brandfolder.io/"
        f"{BRANDFOLDER_CDN_KEY}/at/"
        f"{attachment_id}/{encoded_filename}"
        "?width=800&height=800&pad=true&auto=webp"
    )


def attachment_sort_key(
    attachment: dict[str, Any],
) -> tuple[int, str]:
    attributes = attachment.get("attributes", {})

    try:
        position = int(attributes.get("position", 9999))
    except (TypeError, ValueError):
        position = 9999

    filename = str(
        attributes.get("filename")
        or attributes.get("original_filename")
        or ""
    )

    return position, filename.upper()


def build_index() -> None:
    assets = load_brandfolder_assets()
    woo_skus, woo_products = load_woo_skus()

    woo_skus_sorted = sorted(
        woo_skus,
        key=len,
        reverse=True,
    )

    print("\n" + "=" * 70)
    print("BRANDFOLDER INDEKSA VEIDOŠANA")
    print("=" * 70)
    print(f"Brandfolder aktīvi: {len(assets)}")
    print(f"WooCommerce SKU:   {len(woo_skus)}")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    index: dict[str, dict[str, Any]] = {}
    unmatched: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    session = requests.Session()
    session.headers.update(api_headers())

    for number, asset in enumerate(assets, start=1):
        asset_id = str(asset.get("id") or "")
        attributes = asset.get("attributes", {})
        asset_name = str(attributes.get("name") or "")

        print(
            f"\n[{number}/{len(assets)}] "
            f"{asset_name or asset_id}"
        )

        if not asset_id:
            print("  Izlaists — nav asset ID.")
            continue

        try:
            attachments = get_asset_attachments(
                session=session,
                asset_id=asset_id,
            )
        except requests.RequestException as error:
            print(f"  ❌ API kļūda: {error}")
            errors.append(
                {
                    "asset_id": asset_id,
                    "asset_name": asset_name,
                    "error": str(error),
                }
            )
            continue

        attachments.sort(key=attachment_sort_key)

        matched_for_asset = 0

        for attachment in attachments:
            attachment_id = str(attachment.get("id") or "")
            attachment_attributes = attachment.get(
                "attributes",
                {},
            )

            filename = str(
                attachment_attributes.get("filename")
                or attachment_attributes.get(
                    "original_filename"
                )
                or ""
            ).strip()

            extension = str(
                attachment_attributes.get("extension")
                or ""
            ).lower()

            if not filename or not attachment_id:
                continue

            if extension not in IMAGE_EXTENSIONS:
                continue

if not is_product_image(filename):
    continue

            sku = detect_sku(
                filename=filename,
                woo_skus_sorted=woo_skus_sorted,
            )

            if not sku:
                unmatched.append(
                    {
                        "asset_id": asset_id,
                        "asset_name": asset_name,
                        "attachment_id": attachment_id,
                        "filename": filename,
                        "reason": (
                            "Faila nosaukumā netika atrasts "
                            "WooCommerce SKU."
                        ),
                    }
                )
                continue

            product = woo_products[sku]

            entry = index.setdefault(
                sku,
                {
                    "sku": sku,
                    "woocommerce_id": product.get("id"),
                    "woocommerce_name": product.get("name", ""),
                    "asset_ids": [],
                    "asset_names": [],
                    "images": [],
                },
            )

            if asset_id not in entry["asset_ids"]:
                entry["asset_ids"].append(asset_id)

            if asset_name and asset_name not in entry["asset_names"]:
                entry["asset_names"].append(asset_name)

            cdn_url = make_cdn_url(
                attachment_id=attachment_id,
                filename=filename,
            )

            existing_urls = {
                image["url"]
                for image in entry["images"]
            }

            if cdn_url not in existing_urls:
                entry["images"].append(
                    {
                        "attachment_id": attachment_id,
                        "filename": filename,
                        "position": attachment_attributes.get(
                            "position"
                        ),
                        "url": cdn_url,
                    }
                )

            matched_for_asset += 1

        print(
            f"  Pielikumi: {len(attachments)}, "
            f"SKU sakritības: {matched_for_asset}"
        )

        # Neliela pauze, lai nepārslogotu Brandfolder API.
        time.sleep(0.15)

    # Katrā SKU attēlus sakārto pēc pozīcijas un faila nosaukuma.
    for entry in index.values():
        entry["images"].sort(
            key=lambda image: (
                (
                    image.get("position")
                    if isinstance(
                        image.get("position"),
                        int,
                    )
                    else 9999
                ),
                str(image.get("filename") or "").upper(),
            )
        )

    output_payload = {
        "meta": {
            "brandfolder_assets": len(assets),
            "woocommerce_skus": len(woo_skus),
            "matched_skus": len(index),
            "matched_images": sum(
                len(entry["images"])
                for entry in index.values()
            ),
            "unmatched_attachments": len(unmatched),
            "errors": len(errors),
            "image_width": 800,
            "image_height": 800,
            "format": "webp",
        },
        "products": dict(sorted(index.items())),
    }

    unmatched_payload = {
        "meta": {
            "unmatched_attachments": len(unmatched),
            "errors": len(errors),
        },
        "unmatched": unmatched,
        "errors": errors,
    }

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            output_payload,
            file,
            ensure_ascii=False,
            indent=2,
        )

    with UNMATCHED_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            unmatched_payload,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("\n" + "=" * 70)
    print("INDEKSA KOPSAVILKUMS")
    print("=" * 70)
    print(f"Brandfolder aktīvi:       {len(assets)}")
    print(f"WooCommerce SKU:          {len(woo_skus)}")
    print(f"Atrasti atbilstoši SKU:   {len(index)}")
    print(
        "Atrasti attēli:           "
        f"{sum(len(entry['images']) for entry in index.values())}"
    )
    print(f"Neatpazīti pielikumi:      {len(unmatched)}")
    print(f"API kļūdas:                {len(errors)}")
    print(f"\nIndekss saglabāts:\n{OUTPUT_FILE}")
    print(f"\nNeatpazītie saglabāti:\n{UNMATCHED_FILE}")


if __name__ == "__main__":
    build_index()