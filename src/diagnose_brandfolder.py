#!/usr/bin/env python3

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = PROJECT_ROOT / "cache" / "brandfolder_7032_response.json"

API_BASE_URL = "https://brandfolder.com/api/v4"
COLLECTION_ID = "gss8kc28x4vhgwxk9s3cj3"
TEST_SKU = "7032"

load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.getenv("BRANDFOLDER_API_KEY")


def main() -> None:
    if not API_KEY:
        raise RuntimeError(
            "BRANDFOLDER_API_KEY nav norādīts .env failā."
        )

    response = requests.get(
        f"{API_BASE_URL}/collections/{COLLECTION_ID}/assets",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Accept": "application/json",
        },
        params={
            "search": TEST_SKU,
            "include": "attachments,custom_fields",
            "per": 100,
        },
        timeout=90,
    )

    print(f"HTTP Status: {response.status_code}")

    if not response.ok:
        print(response.text[:2000])
        response.raise_for_status()

    payload: dict[str, Any] = response.json()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("Galvenās atslēgas:", list(payload.keys()))

    data = payload.get("data", [])
    included = payload.get("included", [])

    print("data tips:", type(data).__name__)
    print("data ieraksti:", len(data) if isinstance(data, list) else "nav saraksts")

    print("included tips:", type(included).__name__)
    print(
        "included ieraksti:",
        len(included) if isinstance(included, list) else "nav saraksts",
    )

    all_items: list[dict[str, Any]] = []

    if isinstance(data, list):
        all_items.extend(
            item for item in data if isinstance(item, dict)
        )

    if isinstance(included, list):
        all_items.extend(
            item for item in included if isinstance(item, dict)
        )

    type_counts = Counter(
        str(item.get("type") or "bez tipa")
        for item in all_items
    )

    print("\nAtrasto objektu tipi:")

    for item_type, count in sorted(type_counts.items()):
        print(f"  {item_type}: {count}")

    print("\nCountry - SKU Number vērtības:")

    sku_values_found = 0

    for item in all_items:
        if item.get("type") != "custom_field_values":
            continue

        attributes = item.get("attributes", {})
        key = str(attributes.get("key") or "").strip()
        value = str(attributes.get("value") or "").strip()

        if key.casefold() == "country - sku number".casefold():
            print(f"  {value}")
            sku_values_found += 1

    if sku_values_found == 0:
        print("  Nav atrastas.")

    print("\nPirmie attēlu pielikumi:")

    attachment_count = 0

    for item in all_items:
        if item.get("type") != "attachments":
            continue

        attributes = item.get("attributes", {})
        filename = attributes.get("filename", "")
        position = attributes.get("position", "")

        print(
            f"  {item.get('id', '')} | "
            f"pozīcija {position} | {filename}"
        )

        attachment_count += 1

        if attachment_count >= 15:
            break

    print(f"\nPilnā atbilde saglabāta:\n{OUTPUT_FILE}")


if __name__ == "__main__":
    main()