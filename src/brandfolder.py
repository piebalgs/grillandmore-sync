#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "cache" / "brandfolder"

load_dotenv(PROJECT_ROOT / ".env")


API_BASE_URL = "https://brandfolder.com/api/v4"

BRANDFOLDER_API_KEY = os.getenv("BRANDFOLDER_API_KEY")

BRANDFOLDER_COLLECTION_ID = os.getenv(
    "BRANDFOLDER_COLLECTION_ID",
    "gss8kc28x4vhgwxk9s3cj3",
)

DEFAULT_CDN_KEY = os.getenv(
    "BRANDFOLDER_CDN_KEY",
    "XBRZ2A26",
)

SKU_CUSTOM_FIELD = "Country - SKU Number"

IMAGE_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp",
}

EXCLUDED_FILENAME_MARKERS = {
    "_PKG",
    "-PKG",
    "PACKAGE",
    "_MASTER",
    "-MASTER",
}

CACHE_VERSION = 2


class BrandfolderError(RuntimeError):
    """Brandfolder API vai datu apstrādes kļūda."""


def normalize_sku(value: Any) -> str:
    text = str(value or "").strip().upper()

    if not text:
        return ""

    # Brandfolder dažreiz pievieno reģiona sufiksu:
    # 3400061-AMER
    # 3400134 - Global
    #
    # WooCommerce SKU paliek tikai pamata daļa.
    base_sku = text.split("-", 1)[0].strip()

    return base_sku


def api_headers() -> dict[str, str]:
    if not BRANDFOLDER_API_KEY:
        raise BrandfolderError(
            "BRANDFOLDER_API_KEY nav norādīts .env failā."
        )

    return {
        "Authorization": f"Bearer {BRANDFOLDER_API_KEY}",
        "Accept": "application/json",
    }


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(api_headers())
    return session


def is_product_image(filename: str) -> bool:
    """
    Atļauj:
      7032A1_rgb.png
      7032A2_rgb.png
      7032M1_rgb.jpg
      7032M2.jpg

    Neatļauj:
      7032A_pkg.png
      7032B_master.png
      PDF, XLSX un citus tehniskos failus.
    """
    normalized = filename.strip().upper()

    if not normalized:
        return False

    if any(
        marker in normalized
        for marker in EXCLUDED_FILENAME_MARKERS
    ):
        return False

    if "_RGB" in normalized:
        return True

    if re.search(
        r"(?:^|[^A-Z0-9])M\d+(?:[^A-Z0-9]|$)",
        normalized,
    ):
        return True

    if re.search(
        r"\dM\d+(?:[^A-Z0-9]|$)",
        normalized,
    ):
        return True

    return False


def natural_sort_key(value: str) -> list[Any]:
    parts = re.split(r"(\d+)", value.upper())

    return [
        int(part) if part.isdigit() else part
        for part in parts
    ]


def image_sort_key(image: dict[str, Any]) -> tuple[Any, ...]:
    filename = str(image.get("filename") or "")
    normalized = filename.upper()

    is_lifestyle = bool(
        re.search(r"\dM\d+", normalized)
        or re.search(
            r"(?:^|[^A-Z0-9])M\d+",
            normalized,
        )
    )

    try:
        position = int(image.get("position", 9999))
    except (TypeError, ValueError):
        position = 9999

    return (
        1 if is_lifestyle else 0,
        natural_sort_key(filename),
        position,
    )


def split_sku_values(value: Any) -> list[str]:
    text = str(value or "").strip()

    if not text:
        return []

    parts = re.split(r"[,;\n/]+", text)
    results: list[str] = []

    for part in parts:
        sku = normalize_sku(part)

        if sku and sku not in results:
            results.append(sku)

    return results


def relationship_ids(
    resource: dict[str, Any],
    possible_names: tuple[str, ...],
) -> set[str]:
    relationships = resource.get("relationships", {})

    if not isinstance(relationships, dict):
        return set()

    result: set[str] = set()

    for name in possible_names:
        relationship = relationships.get(name, {})

        if not isinstance(relationship, dict):
            continue

        data = relationship.get("data", [])

        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list):
            continue

        for item in data:
            if not isinstance(item, dict):
                continue

            item_id = str(item.get("id") or "").strip()

            if item_id:
                result.add(item_id)

    return result


def index_included_items(
    included: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    for item in included:
        if not isinstance(item, dict):
            continue

        item_id = str(item.get("id") or "").strip()

        if item_id:
            result[item_id] = item

    return result


def get_asset_cdn_key(
    asset_attributes: dict[str, Any],
) -> str:
    """
    CDN atslēgu vispirms nolasa no aktīva faktiskā cdn_url.

    Piemērs:
      https://cdn.brandfolder.io/6KL7USS2/as/...

    Tad CDN atslēga ir:
      6KL7USS2

    Ja cdn_url nav pieejams, izmanto brandfolder_cdn_key
    vai .env noklusējuma vērtību.
    """
    asset_cdn_url = str(
        asset_attributes.get("cdn_url") or ""
    ).strip()

    if asset_cdn_url:
        parsed = urlparse(asset_cdn_url)

        path_parts = [
            part
            for part in parsed.path.split("/")
            if part
        ]

        if path_parts:
            return path_parts[0]

    cdn_key = str(
        asset_attributes.get("brandfolder_cdn_key")
        or DEFAULT_CDN_KEY
        or ""
    ).strip()

    if not cdn_key:
        raise BrandfolderError(
            "Brandfolder CDN key nav atrasts."
        )

    return cdn_key


def build_cdn_url(
    *,
    cdn_key: str,
    attachment_id: str,
    filename: str,
) -> str:
    encoded_filename = quote(filename, safe="")

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


def get_asset_skus(
    *,
    asset: dict[str, Any],
    included_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    custom_field_ids = relationship_ids(
        asset,
        (
            "custom_fields",
            "custom_field_values",
        ),
    )

    skus: list[str] = []

    for item_id in custom_field_ids:
        item = included_by_id.get(item_id)

        if not item:
            continue

        if item.get("type") != "custom_field_values":
            continue

        attributes = item.get("attributes", {})

        if not isinstance(attributes, dict):
            continue

        key = str(attributes.get("key") or "").strip()

        if key.casefold() != SKU_CUSTOM_FIELD.casefold():
            continue

        for sku in split_sku_values(
            attributes.get("value")
        ):
            if sku not in skus:
                skus.append(sku)

    return skus


def get_asset_images(
    *,
    asset: dict[str, Any],
    included_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    attachment_ids = relationship_ids(
        asset,
        ("attachments",),
    )

    asset_attributes = asset.get("attributes", {})

    if not isinstance(asset_attributes, dict):
        asset_attributes = {}

    cdn_key = get_asset_cdn_key(
        asset_attributes
    )

    images: list[dict[str, Any]] = []

    for attachment_id in attachment_ids:
        attachment = included_by_id.get(attachment_id)

        if not attachment:
            continue

        if attachment.get("type") != "attachments":
            continue

        attributes = attachment.get("attributes", {})

        if not isinstance(attributes, dict):
            continue

        filename = str(
            attributes.get("filename")
            or attributes.get("original_filename")
            or ""
        ).strip()

        extension = str(
            attributes.get("extension")
            or ""
        ).strip().lower()

        if not filename:
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

        original_url = str(
            attributes.get("url") or ""
        ).strip()

        smart_cdn_url = build_cdn_url(
            cdn_key=cdn_key,
            attachment_id=attachment_id,
            filename=filename,
        )

        images.append(
            {
                "attachment_id": attachment_id,
                "filename": filename,
                "extension": extension,
                "position": position,
                "width": attributes.get("width"),
                "height": attributes.get("height"),
                "cdn_key": cdn_key,
                "cdn_url": smart_cdn_url,
                "original_url": original_url,
                "url": original_url or smart_cdn_url,
            }
        )

    images.sort(key=image_sort_key)

    return images


def search_collection(
    sku: str,
    *,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    normalized_sku = normalize_sku(sku)

    if not normalized_sku:
        raise ValueError("SKU nedrīkst būt tukšs.")

    if not BRANDFOLDER_COLLECTION_ID:
        raise BrandfolderError(
            "BRANDFOLDER_COLLECTION_ID nav norādīts."
        )

    close_session = session is None

    if session is None:
        session = create_session()

    try:
        response = session.get(
            (
                f"{API_BASE_URL}/collections/"
                f"{BRANDFOLDER_COLLECTION_ID}/assets"
            ),
            params={
                "search": normalized_sku,
                "include": (
                    "attachments,"
                    "custom_fields"
                ),
                "per": 100,
            },
            timeout=90,
        )

        if not response.ok:
            raise BrandfolderError(
                f"Brandfolder HTTP {response.status_code}: "
                f"{response.text[:1000]}"
            )

        payload = response.json()

        if not isinstance(payload, dict):
            raise BrandfolderError(
                "Brandfolder atgrieza negaidītu datu formātu."
            )

        return payload

    finally:
        if close_session:
            session.close()


def parse_search_response(
    payload: dict[str, Any],
    requested_sku: str,
) -> list[dict[str, Any]]:
    normalized_sku = normalize_sku(requested_sku)

    data = payload.get("data", [])
    included = payload.get("included", [])

    if not isinstance(data, list):
        data = []

    if not isinstance(included, list):
        included = []

    included_by_id = index_included_items(included)

    matches: list[dict[str, Any]] = []

    for asset in data:
        if not isinstance(asset, dict):
            continue

        if asset.get("type") not in {
            "generic_files",
            "assets",
        }:
            continue

        asset_skus = get_asset_skus(
            asset=asset,
            included_by_id=included_by_id,
        )

        normalized_asset_skus = {
            normalize_sku(value)
            for value in asset_skus
        }

        if normalized_sku not in normalized_asset_skus:
            continue

        asset_attributes = asset.get("attributes", {})

        if not isinstance(asset_attributes, dict):
            asset_attributes = {}

        images = get_asset_images(
            asset=asset,
            included_by_id=included_by_id,
        )

        matches.append(
            {
                "asset_id": str(
                    asset.get("id") or ""
                ),
                "asset_name": str(
                    asset_attributes.get("name")
                    or ""
                ),
                "cdn_key": get_asset_cdn_key(
                    asset_attributes
                ),
                "skus": asset_skus,
                "images": images,
            }
        )

    return matches


def normalized_image_filename(filename: str) -> str:
    stem = Path(filename).stem.upper()

    stem = re.sub(r"-SCALED$", "", stem)
    stem = re.sub(r"-\d+$", "", stem)
    stem = re.sub(r"[\s_-]+", "", stem)

    return stem


def merge_asset_images(
    assets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Vienam SKU Brandfolder var atgriezt vairākus aktīvus
    ar vienādiem failiem.

    Atstājam tikai vienu attēlu katram normalizētam
    faila nosaukumam.
    """
    images_by_filename: dict[
        str,
        dict[str, Any],
    ] = {}

    for asset in assets:
        for image in asset.get("images", []):
            filename = str(
                image.get("filename") or ""
            ).strip()

            if not filename:
                continue

            key = normalized_image_filename(filename)

            current = images_by_filename.get(key)

            if current is None:
                images_by_filename[key] = image
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
                images_by_filename[key] = image

    images = list(images_by_filename.values())
    images.sort(key=image_sort_key)

    return images


def cache_file_for_sku(sku: str) -> Path:
    safe_sku = re.sub(
        r"[^A-Z0-9._-]+",
        "_",
        normalize_sku(sku),
    )

    return CACHE_DIR / f"{safe_sku}.json"


def load_cached_images(
    sku: str,
) -> list[dict[str, Any]] | None:
    cache_file = cache_file_for_sku(sku)

    if not cache_file.exists():
        return None

    try:
        with cache_file.open(
            "r",
            encoding="utf-8",
        ) as file:
            payload = json.load(file)
    except (OSError, json.JSONDecodeError):
        return None

    if payload.get("cache_version") != CACHE_VERSION:
        return None

    images = payload.get("images")

    return images if isinstance(images, list) else None


def save_cached_images(
    sku: str,
    assets: list[dict[str, Any]],
    images: list[dict[str, Any]],
) -> None:
    CACHE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "cache_version": CACHE_VERSION,
        "sku": normalize_sku(sku),
        "assets": [
            {
                "asset_id": asset.get("asset_id"),
                "asset_name": asset.get("asset_name"),
                "cdn_key": asset.get("cdn_key"),
            }
            for asset in assets
        ],
        "images": images,
    }

    with cache_file_for_sku(sku).open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
        )


def get_product_images(
    sku: str,
    *,
    use_cache: bool = False,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    normalized_sku = normalize_sku(sku)

    if not normalized_sku:
        return []

    if use_cache:
        cached = load_cached_images(normalized_sku)

        if cached is not None:
            return cached

    payload = search_collection(
        normalized_sku,
        session=session,
    )

    matching_assets = parse_search_response(
        payload,
        normalized_sku,
    )

    images = merge_asset_images(
        matching_assets
    )

    save_cached_images(
        normalized_sku,
        matching_assets,
        images,
    )

    return images


def diagnose_sku(sku: str) -> None:
    normalized_sku = normalize_sku(sku)

    payload = search_collection(normalized_sku)

    matches = parse_search_response(
        payload,
        normalized_sku,
    )

    print("=" * 70)
    print("BRANDFOLDER PRODUKTA ATTĒLI")
    print("=" * 70)
    print(f"SKU:             {normalized_sku}")
    print(f"Atrasti aktīvi:  {len(matches)}")

    for asset_number, asset in enumerate(
        matches,
        start=1,
    ):
        print("\n" + "-" * 70)
        print(
            f"Aktīvs {asset_number}: "
            f"{asset.get('asset_name', '')}"
        )
        print(
            f"Asset ID: "
            f"{asset.get('asset_id', '')}"
        )
        print(
            f"CDN key:  "
            f"{asset.get('cdn_key', '')}"
        )
        print(
            f"Attēli:    "
            f"{len(asset.get('images', []))}"
        )

        for image in asset.get("images", []):
            print(
                f"  {image.get('filename', '')}"
            )
            print(
                f"    {image.get('url', '')}"
            )

    images = merge_asset_images(matches)

    print("\n" + "=" * 70)
    print(f"Unikālo produktu attēlu skaits: {len(images)}")
    print("=" * 70)

    for number, image in enumerate(
        images,
        start=1,
    ):
        print(
            f"{number}. "
            f"{image.get('filename', '')}"
        )
        print(
            f"   CDN key: {image.get('cdn_key', '')}"
        )
        print(
            f"   {image.get('url', '')}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Meklē produkta attēlus Brandfolder "
            "pēc Country - SKU Number."
        )
    )

    parser.add_argument(
        "sku",
        help="WooCommerce SKU, piemēram, 7032.",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Izvadīt rezultātu JSON formātā.",
    )

    parser.add_argument(
        "--cache",
        action="store_true",
        help="Atļaut izmantot saglabātu kešatmiņu.",
    )

    args = parser.parse_args()

    if args.json:
        images = get_product_images(
            args.sku,
            use_cache=args.cache,
        )

        print(
            json.dumps(
                images,
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    diagnose_sku(args.sku)


if __name__ == "__main__":
    main()