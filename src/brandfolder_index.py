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


load_dotenv(".env")


PROJECT_ROOT = Path(__file__).resolve().parent.parent

SOURCE_FILE = (
    PROJECT_ROOT
    / "supplier"
    / "brandfolder_assets.json"
)

OUTPUT_FILE = (
    PROJECT_ROOT
    / "cache"
    / "brandfolder_index.json"
)

UNMATCHED_FILE = (
    PROJECT_ROOT
    / "cache"
    / "brandfolder_unmatched.json"
)


BRANDFOLDER_API_KEY = os.getenv("BRANDFOLDER_API_KEY")

DEFAULT_CDN_KEY = os.getenv(
    "BRANDFOLDER_CDN_KEY",
    "XBRZ2A26",
)

API_BASE_URL = "https://brandfolder.com/api/v4"

SKU_CUSTOM_FIELD = "Country - SKU Number"

IMAGE_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp",
}


def normalize_sku(value: Any) -> str:
    return str(value or "").strip().upper()


def api_headers() -> dict[str, str]:
    if not BRANDFOLDER_API_KEY:
        raise RuntimeError(
            "BRANDFOLDER_API_KEY nav norādīts .env failā."
        )

    return {
        "Authorization": (
            f"Bearer {BRANDFOLDER_API_KEY}"
        ),
        "Accept": "application/json",
    }


def load_source_assets() -> list[dict[str, Any]]:
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(
            f"Brandfolder fails nav atrasts: {SOURCE_FILE}"
        )

    with SOURCE_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        payload = json.load(file)

    if not isinstance(payload, dict):
        raise ValueError(
            "Brandfolder JSON galvenajam elementam "
            "jābūt objektam."
        )

    assets = payload.get("data", [])

    if not isinstance(assets, list):
        raise ValueError(
            "Brandfolder JSON laukam 'data' "
            "jābūt sarakstam."
        )

    return assets


def load_woocommerce_index(
) -> dict[str, dict[str, Any]]:
    products = load_woocommerce_products()

    index: dict[str, dict[str, Any]] = {}

    for product in products:
        sku = normalize_sku(product.get("sku"))

        if sku:
            index[sku] = product

    return index


def get_asset_details(
    session: requests.Session,
    asset_id: str,
) -> dict[str, Any]:
    response = session.get(
        f"{API_BASE_URL}/assets/{asset_id}",
        params={
            "include": (
                "attachments,"
                "custom_field_values"
            ),
        },
        timeout=90,
    )

    if not response.ok:
        error_text = response.text[:1000]

        raise requests.HTTPError(
            f"Asset {asset_id}: "
            f"HTTP {response.status_code}: "
            f"{error_text}",
            response=response,
        )

    payload = response.json()

    if not isinstance(payload, dict):
        raise ValueError(
            f"Asset {asset_id}: "
            "negaidīts API atbildes formāts."
        )

    return payload


def collect_included_items(
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Brandfolder dažādos endpointos saistītos
    objektus var atgriezt laukā 'included'
    vai reizēm kā sarakstu laukā 'data'.

    Funkcija atbalsta abus variantus.
    """
    items: list[dict[str, Any]] = []

    included = payload.get("included", [])

    if isinstance(included, list):
        items.extend(
            item
            for item in included
            if isinstance(item, dict)
        )

    data = payload.get("data")

    if isinstance(data, list):
        items.extend(
            item
            for item in data
            if isinstance(item, dict)
            and item.get("type") in {
                "attachments",
                "custom_field_values",
            }
        )

    return items


def extract_skus_from_value(
    value: Any,
) -> list[str]:
    """
    Atbalsta vienu vai vairākus SKU vienā laukā.

    Piemēri:
      7032
      7032, 7033
      7032;7033
      7032 / 7033
    """
    text = str(value or "").strip()

    if not text:
        return []

    parts = re.split(
        r"[,;\n/]+",
        text,
    )

    skus: list[str] = []

    for part in parts:
        sku = normalize_sku(part)

        if sku and sku not in skus:
            skus.append(sku)

    return skus


def extract_asset_skus(
    included_items: list[dict[str, Any]],
) -> list[str]:
    skus: list[str] = []

    for item in included_items:
        if item.get("type") != "custom_field_values":
            continue

        attributes = item.get("attributes", {})

        key = str(
            attributes.get("key") or ""
        ).strip()

        if key.casefold() != SKU_CUSTOM_FIELD.casefold():
            continue

        values = extract_skus_from_value(
            attributes.get("value")
        )

        for sku in values:
            if sku not in skus:
                skus.append(sku)

    return skus


def is_product_image(filename: str) -> bool:
    """
    Importējam:
      *_rgb
      M1, M2, M3 utt.

    Neimportējam:
      *_pkg
      *_master
      tehniskos vai iepakojuma failus
    """
    normalized = filename.upper()

    excluded_markers = (
        "_PKG",
        "-PKG",
        "PACKAGE",
        "_MASTER",
        "-MASTER",
    )

    if any(
        marker in normalized
        for marker in excluded_markers
    ):
        return False

    if "_RGB" in normalized:
        return True

    # Atbalsta, piemēram:
    # 7032M1.jpg
    # 7032_M1.jpg
    # product-M2-image.png
    if re.search(
        r"(?:^|[^A-Z0-9])M\d+(?:[^A-Z0-9]|$)",
        normalized,
    ):
        return True

    # Atbalsta arī 7032M1.jpg,
    # kur pirms M nav atdalītāja.
    if re.search(
        r"\dM\d+(?:[^A-Z0-9]|$)",
        normalized,
    ):
        return True

    return False


def get_image_attachments(
    included_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []

    for item in included_items:
        if item.get("type") != "attachments":
            continue

        attachment_id = str(
            item.get("id") or ""
        ).strip()

        attributes = item.get("attributes", {})

        filename = str(
            attributes.get("filename")
            or attributes.get("original_filename")
            or ""
        ).strip()

        extension = str(
            attributes.get("extension")
            or ""
        ).strip().lower()

        if not attachment_id or not filename:
            continue

        if extension not in IMAGE_EXTENSIONS:
            continue

        if not is_product_image(filename):
            continue

        try:
            position = int(
                attributes.get("position", 9999)
            )
        except (TypeError, ValueError):
            position = 9999

        images.append(
            {
                "attachment_id": attachment_id,
                "filename": filename,
                "position": position,
            }
        )

    images.sort(
        key=lambda image: (
            image["position"],
            image["filename"].upper(),
        )
    )

    return images


def get_asset_cdn_key(
    source_asset: dict[str, Any],
) -> str:
    attributes = source_asset.get(
        "attributes",
        {},
    )

    cdn_key = str(
        attributes.get("brandfolder_cdn_key")
        or DEFAULT_CDN_KEY
        or ""
    ).strip()

    if not cdn_key:
        raise RuntimeError(
            "Brandfolder CDN key nav atrasts."
        )

    return cdn_key


def make_cdn_url(
    cdn_key: str,
    attachment_id: str,
    filename: str,
) -> str:
    encoded_filename = quote(
        filename,
        safe="",
    )

    return (
        f"https://cdn.brandfolder.io/"
        f"{cdn_key}/at/"
        f"{attachment_id}/"
        f"{encoded_filename}"
        "?width=800"
        "&height=800"
        "&pad=true"
        "&auto=webp"
    )


def merge_product_images(
    index: dict[str, dict[str, Any]],
    sku: str,
    woo_product: dict[str, Any],
    asset_id: str,
    asset_name: str,
    images: list[dict[str, Any]],
    cdn_key: str,
) -> None:
    entry = index.setdefault(
        sku,
        {
            "sku": sku,
            "woocommerce_id": woo_product.get("id"),
            "woocommerce_name": woo_product.get(
                "name",
                "",
            ),
            "asset_ids": [],
            "asset_names": [],
            "images": [],
        },
    )

    if asset_id not in entry["asset_ids"]:
        entry["asset_ids"].append(asset_id)

    if (
        asset_name
        and asset_name not in entry["asset_names"]
    ):
        entry["asset_names"].append(asset_name)

    existing_attachment_ids = {
        image.get("attachment_id")
        for image in entry["images"]
    }

    for image in images:
        attachment_id = image["attachment_id"]

        if attachment_id in existing_attachment_ids:
            continue

        entry["images"].append(
            {
                "attachment_id": attachment_id,
                "filename": image["filename"],
                "position": image["position"],
                "url": make_cdn_url(
                    cdn_key=cdn_key,
                    attachment_id=attachment_id,
                    filename=image["filename"],
                ),
            }
        )

        existing_attachment_ids.add(
            attachment_id
        )


def sort_index_images(
    index: dict[str, dict[str, Any]],
) -> None:
    for entry in index.values():
        entry["images"].sort(
            key=lambda image: (
                image.get("position", 9999),
                str(
                    image.get("filename") or ""
                ).upper(),
            )
        )


def build_index() -> None:
    assets = load_source_assets()
    woo_index = load_woocommerce_index()

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    index: dict[str, dict[str, Any]] = {}

    unmatched_assets: list[dict[str, Any]] = []
    skipped_skus: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    session = requests.Session()
    session.headers.update(api_headers())

    print("\n" + "=" * 70)
    print("BRANDFOLDER INDEKSA VEIDOŠANA")
    print("=" * 70)
    print(f"Brandfolder aktīvi: {len(assets)}")
    print(f"WooCommerce SKU:   {len(woo_index)}")

    for number, source_asset in enumerate(
        assets,
        start=1,
    ):
        asset_id = str(
            source_asset.get("id") or ""
        ).strip()

        source_attributes = source_asset.get(
            "attributes",
            {},
        )

        asset_name = str(
            source_attributes.get("name") or ""
        ).strip()

        print(
            f"\n[{number}/{len(assets)}] "
            f"{asset_name or asset_id}"
        )

        if not asset_id:
            print("  Izlaists — nav asset ID.")

            unmatched_assets.append(
                {
                    "asset_name": asset_name,
                    "reason": "Nav asset ID.",
                }
            )
            continue

        try:
            payload = get_asset_details(
                session=session,
                asset_id=asset_id,
            )

            included_items = collect_included_items(
                payload
            )

            skus = extract_asset_skus(
                included_items
            )

            images = get_image_attachments(
                included_items
            )

            cdn_key = get_asset_cdn_key(
                source_asset
            )

        except (
            requests.RequestException,
            RuntimeError,
            ValueError,
        ) as error:
            print(f"  ❌ Kļūda: {error}")

            errors.append(
                {
                    "asset_id": asset_id,
                    "asset_name": asset_name,
                    "error": str(error),
                }
            )
            continue

        if not skus:
            print(
                "  Izlaists — nav "
                "'Country - SKU Number'."
            )

            unmatched_assets.append(
                {
                    "asset_id": asset_id,
                    "asset_name": asset_name,
                    "reason": (
                        "Nav Country - SKU Number."
                    ),
                }
            )
            continue

        print(
            f"  SKU metadatos: {', '.join(skus)}"
        )
        print(
            f"  Produktu attēli: {len(images)}"
        )

        matched_for_asset = 0

        for sku in skus:
            woo_product = woo_index.get(sku)

            if not woo_product:
                print(
                    f"  SKU {sku}: "
                    "nav WooCommerce — izlaists."
                )

                skipped_skus.append(
                    {
                        "asset_id": asset_id,
                        "asset_name": asset_name,
                        "sku": sku,
                        "reason": (
                            "SKU nav WooCommerce."
                        ),
                    }
                )
                continue

            if not images:
                print(
                    f"  SKU {sku}: "
                    "nav derīgu produktu attēlu."
                )

                unmatched_assets.append(
                    {
                        "asset_id": asset_id,
                        "asset_name": asset_name,
                        "sku": sku,
                        "reason": (
                            "Nav _rgb vai M* "
                            "produktu attēlu."
                        ),
                    }
                )
                continue

            merge_product_images(
                index=index,
                sku=sku,
                woo_product=woo_product,
                asset_id=asset_id,
                asset_name=asset_name,
                images=images,
                cdn_key=cdn_key,
            )

            matched_for_asset += 1

        print(
            "  WooCommerce sakritības: "
            f"{matched_for_asset}"
        )

        # Saudzīga pauze API pieprasījumiem.
        time.sleep(0.15)

    sort_index_images(index)

    matched_images = sum(
        len(entry["images"])
        for entry in index.values()
    )

    output_payload = {
        "meta": {
            "brandfolder_assets": len(assets),
            "woocommerce_skus": len(woo_index),
            "matched_skus": len(index),
            "matched_images": matched_images,
            "unmatched_assets": len(
                unmatched_assets
            ),
            "skipped_skus": len(skipped_skus),
            "errors": len(errors),
            "image_width": 800,
            "image_height": 800,
            "image_format": "webp",
            "sku_source": SKU_CUSTOM_FIELD,
            "included_images": [
                "*_rgb",
                "*M1*",
                "*M2*",
                "*M3*",
            ],
            "excluded_images": [
                "*_pkg",
                "*_master",
            ],
        },
        "products": dict(
            sorted(index.items())
        ),
    }

    unmatched_payload = {
        "meta": {
            "unmatched_assets": len(
                unmatched_assets
            ),
            "skipped_skus": len(skipped_skus),
            "errors": len(errors),
        },
        "unmatched_assets": unmatched_assets,
        "skipped_skus": skipped_skus,
        "errors": errors,
    }

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            output_payload,
            file,
            ensure_ascii=False,
            indent=2,
        )

    with UNMATCHED_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            unmatched_payload,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("\n" + "=" * 70)
    print("INDEKSA KOPSAVILKUMS")
    print("=" * 70)
    print(
        f"Brandfolder aktīvi:       "
        f"{len(assets)}"
    )
    print(
        f"WooCommerce SKU:          "
        f"{len(woo_index)}"
    )
    print(
        f"Atrasti atbilstoši SKU:   "
        f"{len(index)}"
    )
    print(
        f"Atrasti produktu attēli:  "
        f"{matched_images}"
    )
    print(
        f"Aktīvi bez atbilstoša SKU:"
        f" {len(unmatched_assets)}"
    )
    print(
        f"SKU, kas nav WooCommerce: "
        f"{len(skipped_skus)}"
    )
    print(
        f"API kļūdas:               "
        f"{len(errors)}"
    )

    print(
        "\nIndekss saglabāts:\n"
        f"{OUTPUT_FILE}"
    )

    print(
        "\nNeatpazītie saglabāti:\n"
        f"{UNMATCHED_FILE}"
    )


if __name__ == "__main__":
    build_index()