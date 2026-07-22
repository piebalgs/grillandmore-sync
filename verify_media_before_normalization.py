#!/usr/bin/env python3

import argparse
import csv
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests

PROJECT_DIR = Path(__file__).resolve().parent
SRC_DIR = PROJECT_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from brandfolder import create_session, get_product_images, normalize_sku
from woocommerce import load_products


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pārbauda WooCommerce un Brandfolder produktu attēlus."
    )
    parser.add_argument(
        "--brand",
        help="Filtrēt produktus pēc zīmola, piemēram, Weber.",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Izlaist pirmos N produktus.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Pārbaudīt ne vairāk kā N produktus.",
    )
    parser.add_argument(
        "--cache",
        action="store_true",
        help="Izmantot Brandfolder kešatmiņu.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Rādīt detalizētu informāciju.",
    )
    parser.add_argument(
        "--output",
        default="reports/verify_media.csv",
        help="CSV atskaites ceļš.",
    )
    return parser.parse_args()


def normalized_filename(value: Any) -> str:
    text = str(value or "").strip()

    if not text:
        return ""

    parsed = urlparse(text)
    path = parsed.path if parsed.scheme else text
    filename = unquote(os.path.basename(path)).strip().lower()

    if not filename:
        return ""

    stem, extension = os.path.splitext(filename)

    for suffix in (
        "-scaled",
        "-300x300",
        "-600x600",
        "-768x768",
        "-1024x1024",
        "-1536x1536",
        "-2048x2048",
    ):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break

    return stem


def product_matches_brand(product: dict[str, Any], brand: str | None) -> bool:
    if not brand:
        return True

    search_value = brand.strip().lower()

    if not search_value:
        return True

    values: list[str] = [
        str(product.get("name", "")),
        str(product.get("slug", "")),
    ]

    for field_name in ("categories", "tags", "brands"):
        for item in product.get(field_name, []) or []:
            if isinstance(item, dict):
                values.append(str(item.get("name", "")))
                values.append(str(item.get("slug", "")))
            else:
                values.append(str(item))

    for attribute in product.get("attributes", []) or []:
        if not isinstance(attribute, dict):
            continue

        values.append(str(attribute.get("name", "")))

        for option in attribute.get("options", []) or []:
            values.append(str(option))

    haystack = " ".join(values).lower()
    return search_value in haystack


def get_wc_images(product: dict[str, Any]) -> list[dict[str, Any]]:
    images = product.get("images", [])

    if not isinstance(images, list):
        return []

    return [
        image
        for image in images
        if isinstance(image, dict)
    ]


def get_image_value(image: dict[str, Any]) -> str:
    for key in (
        "src",
        "url",
        "cdn_url",
        "download_url",
        "original_url",
        "filename",
        "name",
    ):
        value = image.get(key)

        if value:
            return str(value)

    return ""


def duplicate_count(values: list[str]) -> int:
    cleaned = [
        value
        for value in values
        if value
    ]
    return len(cleaned) - len(set(cleaned))


def verify_product(
    product: dict[str, Any],
    *,
    use_cache: bool,
    session: requests.Session,
) -> dict[str, Any]:
    raw_sku = product.get("sku", "")
    sku = normalize_sku(raw_sku)
    name = str(product.get("name", "")).strip()

    wc_images = get_wc_images(product)
    wc_values = [
        get_image_value(image)
        for image in wc_images
    ]
    wc_names = [
        normalized_filename(value)
        for value in wc_values
    ]

    if not sku:
        return {
            "status": "FAIL",
            "sku": "",
            "name": name,
            "wc_count": len(wc_images),
            "brandfolder_count": 0,
            "missing_count": 0,
            "extra_count": 0,
            "duplicate_count": duplicate_count(wc_names),
            "message": "Produktam nav SKU.",
            "missing_images": "",
            "extra_images": "",
        }

    try:
        brandfolder_images = get_product_images(
            sku,
            use_cache=use_cache,
            session=session,
        )
    except Exception as exc:
        return {
            "status": "FAIL",
            "sku": sku,
            "name": name,
            "wc_count": len(wc_images),
            "brandfolder_count": 0,
            "missing_count": 0,
            "extra_count": 0,
            "duplicate_count": duplicate_count(wc_names),
            "message": f"Brandfolder kļūda: {exc}",
            "missing_images": "",
            "extra_images": "",
        }

    bf_values = [
        get_image_value(image)
        for image in brandfolder_images
        if isinstance(image, dict)
    ]
    bf_names = [
        normalized_filename(value)
        for value in bf_values
    ]

    wc_set = {
        name
        for name in wc_names
        if name
    }
    bf_set = {
        name
        for name in bf_names
        if name
    }

    missing = sorted(bf_set - wc_set)
    extra = sorted(wc_set - bf_set)
    duplicates = duplicate_count(wc_names)

    if not brandfolder_images and not wc_images:
        status = "WARNING"
        message = "Attēli nav ne WooCommerce, ne Brandfolder."
    elif not brandfolder_images:
        status = "WARNING"
        message = "Brandfolder attēli nav atrasti."
    elif not wc_images:
        status = "FAIL"
        message = "WooCommerce produktam nav attēlu."
    elif missing:
        status = "FAIL"
        message = f"WooCommerce trūkst {len(missing)} Brandfolder attēli."
    elif duplicates:
        status = "WARNING"
        message = f"WooCommerce atrasti {duplicates} attēlu dublikāti."
    elif len(wc_images) > 10:
        status = "WARNING"
        message = "WooCommerce ir vairāk nekā 10 attēli."
    else:
        status = "PASS"
        message = "Attēli atbilst."

    return {
        "status": status,
        "sku": sku,
        "name": name,
        "wc_count": len(wc_images),
        "brandfolder_count": len(brandfolder_images),
        "missing_count": len(missing),
        "extra_count": len(extra),
        "duplicate_count": duplicates,
        "message": message,
        "missing_images": " | ".join(missing),
        "extra_images": " | ".join(extra),
    }


def write_report(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = [
        "status",
        "sku",
        "name",
        "wc_count",
        "brandfolder_count",
        "missing_count",
        "extra_count",
        "duplicate_count",
        "message",
        "missing_images",
        "extra_images",
    ]

    with output_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()

    if args.offset < 0:
        print("Kļūda: --offset nevar būt negatīvs.")
        return 2

    if args.limit is not None and args.limit < 1:
        print("Kļūda: --limit jābūt vismaz 1.")
        return 2

    products = load_products()

    products = [
        product
        for product in products
        if product_matches_brand(product, args.brand)
    ]

    if args.brand:
        print(
            f'Pēc zīmola filtra "{args.brand}" '
            f"atrasti {len(products)} produkti."
        )

    start = args.offset
    end = None if args.limit is None else start + args.limit
    selected_products = products[start:end]

    print(
        f"Pārbaudīs {len(selected_products)} produktus "
        f"no offset {args.offset}."
    )

    session = create_session()
    rows: list[dict[str, Any]] = []

    for index, product in enumerate(
        selected_products,
        start=1,
    ):
        sku = normalize_sku(product.get("sku", ""))
        name = str(product.get("name", "")).strip()

        print(
            f"[{index}/{len(selected_products)}] "
            f"{sku or '(nav SKU)'} | {name}"
        )

        result = verify_product(
            product,
            use_cache=args.cache,
            session=session,
        )
        rows.append(result)

        print(
            f"  {result['status']}: "
            f"WC={result['wc_count']}, "
            f"BF={result['brandfolder_count']} — "
            f"{result['message']}"
        )

        if args.verbose:
            if result["missing_images"]:
                print(
                    f"  Trūkst: {result['missing_images']}"
                )

            if result["extra_images"]:
                print(
                    f"  Papildu WC: {result['extra_images']}"
                )

    output_path = PROJECT_DIR / args.output
    write_report(rows, output_path)

    status_counts = {
        "PASS": 0,
        "WARNING": 0,
        "FAIL": 0,
    }

    for row in rows:
        status = str(row["status"])
        status_counts[status] = status_counts.get(status, 0) + 1

    print("\nPārbaude pabeigta.")
    print(f"PASS:    {status_counts.get('PASS', 0)}")
    print(f"WARNING: {status_counts.get('WARNING', 0)}")
    print(f"FAIL:    {status_counts.get('FAIL', 0)}")
    print(f"Atskaite: {output_path}")

    return 1 if status_counts.get("FAIL", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
