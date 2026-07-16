#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_FILE = PROJECT_ROOT / "cache" / "brandfolder_index.json"

WC_URL = os.getenv("WC_URL", "").rstrip("/")
WC_KEY = os.getenv("WC_CONSUMER_KEY")
WC_SECRET = os.getenv("WC_CONSUMER_SECRET")


def load_index() -> dict[str, dict[str, Any]]:
    if not INDEX_FILE.exists():
        raise FileNotFoundError(
            "Brandfolder indekss nav atrasts. "
            "Vispirms palaid: python3 -m src.build_brandfolder_index"
        )

    with INDEX_FILE.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    products = payload.get("products", {})

    if not isinstance(products, dict):
        raise ValueError("Indeksa laukam 'products' jābūt objektam.")

    return products


def update_product_images(
    product_id: int,
    images: list[dict[str, Any]],
) -> dict[str, Any]:
    if not WC_URL or not WC_KEY or not WC_SECRET:
        raise RuntimeError(
            "WooCommerce piekļuves dati nav norādīti .env failā."
        )

    payload = {
        "images": [
            {
                "src": image["url"],
                "name": image["filename"],
                "alt": image["filename"].rsplit(".", 1)[0],
            }
            for image in images
        ]
    }

    response = requests.put(
        f"{WC_URL}/wp-json/wc/v3/products/{product_id}",
        auth=(WC_KEY, WC_SECRET),
        json=payload,
        timeout=(30, 600),
    )

    if not response.ok:
        print(response.text[:1000])

    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sinhronizē WooCommerce attēlus no Brandfolder indeksa."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Reāli atjaunināt WooCommerce.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Apstrādāt tikai pirmos N produktus.",
    )
    parser.add_argument(
        "--sku",
        help="Apstrādāt tikai vienu konkrētu SKU.",
    )
    args = parser.parse_args()

    products = load_index()

    if args.sku:
        sku = args.sku.strip().upper()
        products = (
            {sku: products[sku]}
            if sku in products
            else {}
        )

    items = list(sorted(products.items()))

    if args.limit is not None:
        items = items[:args.limit]

    print("=" * 70)
    print("BRANDFOLDER → WOOCOMMERCE ATTĒLU SINHRONIZĀCIJA")
    print("=" * 70)
    print(f"Produkti apstrādei: {len(items)}")
    print(
        "Režīms: "
        + ("REĀLA SINHRONIZĀCIJA" if args.apply else "DRY RUN")
    )

    updated = 0
    skipped = 0
    failed = 0

    for number, (sku, entry) in enumerate(items, start=1):
        images = entry.get("images", [])
        product_id = entry.get("woocommerce_id")
        name = entry.get("woocommerce_name", "")

        print("\n" + "-" * 70)
        print(f"[{number}/{len(items)}] {sku} | {name}")
        print(f"WooCommerce ID: {product_id}")
        print(f"Attēlu skaits: {len(images)}")

        if not product_id or not images:
            print("Izlaists — trūkst produkta ID vai attēlu.")
            skipped += 1
            continue

        for image in images:
            print(f"  - {image.get('filename', '')}")

        if not args.apply:
            print("DRY RUN — izmaiņas netika veiktas.")
            continue

        try:
            updated_product = update_product_images(
                product_id=int(product_id),
                images=images,
            )

            print(
                "✅ Atjaunināts. WooCommerce attēlu skaits: "
                f"{len(updated_product.get('images', []))}"
            )
            updated += 1

        except requests.RequestException as error:
            print(f"❌ Kļūda: {error}")
            failed += 1

    print("\n" + "=" * 70)
    print("KOPSAVILKUMS")
    print("=" * 70)
    print(f"Apstrādei:    {len(items)}")
    print(f"Atjaunināti: {updated}")
    print(f"Izlaisti:    {skipped}")
    print(f"Kļūdas:      {failed}")


if __name__ == "__main__":
    main()