#!/usr/bin/env python3

import argparse
import os

import requests
from dotenv import load_dotenv

from src.woocommerce import load_products

load_dotenv()

WC_URL = os.getenv("WC_URL", "").rstrip("/")
WC_KEY = os.getenv("WC_CONSUMER_KEY")
WC_SECRET = os.getenv("WC_CONSUMER_SECRET")


def find_woo_product_by_sku(sku: str) -> dict | None:
    normalized_sku = sku.strip().upper()

    for product in load_products():
        product_sku = str(product.get("sku", "")).strip().upper()

        if product_sku == normalized_sku:
            return product

    return None


def update_images(product_id: int, image_urls: list[str]) -> dict:
    if not WC_URL or not WC_KEY or not WC_SECRET:
        raise RuntimeError(
            "WooCommerce piekļuves dati nav norādīti .env failā."
        )

    payload = {
        "images": [{"src": url} for url in image_urls]
    }

    response = requests.put(
        f"{WC_URL}/wp-json/wc/v3/products/{product_id}",
        auth=(WC_KEY, WC_SECRET),
        json=payload,
        timeout=180,
    )

    if not response.ok:
        print(response.text)

    response.raise_for_status()
    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pārbauda vai pievieno attēlus vienam WooCommerce produktam."
    )
    parser.add_argument("sku")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    product = find_woo_product_by_sku(args.sku)

    if not product:
        print(f"SKU {args.sku} WooCommerce netika atrasts.")
        return

 image_urls = [
    "https://cdn.brandfolder.io/XBRZ2A26/at/s694bkgm3tp55h2twchp5885/7032A1_rgb.png?width=800&height=800&pad=true&auto=webp",
]

    print(f"SKU: {args.sku}")
    print(f"Produkts: {product.get('name')}")
    print(f"WooCommerce ID: {product.get('id')}")
    print(f"Attēlu skaits: {len(image_urls)}")

    for index, url in enumerate(image_urls, start=1):
        print(f"{index}. {url}")

    if not args.apply:
        print("\nDRY RUN — WooCommerce nekas netika mainīts.")
        print(
            f"Lai importētu attēlus, palaid: "
            f"python3 update_images_one.py {args.sku} --apply"
        )
        return

    print("\nImportē attēlus WooCommerce...")

    updated = update_images(
        product_id=product["id"],
        image_urls=image_urls,
    )

    print("\n✅ Attēli veiksmīgi pievienoti.")
    print(f"Produkts: {updated.get('name')}")
    print(
        f"Attēlu skaits WooCommerce: "
        f"{len(updated.get('images', []))}"
    )


if __name__ == "__main__":
    main()