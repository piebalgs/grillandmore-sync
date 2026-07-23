#!/usr/bin/env python3

from __future__ import annotations

import argparse
from typing import Any

from src.brandfolder import (
    create_session as create_brandfolder_session,
)
from src.media.planner import normalize_sku
from src.media.product_processor import process_product
from src.media.reporting import (
    print_sync_summary,
    sync_exit_code,
)
from src.media.html_report import generate_html_report
from src.woocommerce import get_product_by_sku, load_products

def find_product_by_sku(
    products: list[dict[str, Any]],
    sku: str,
) -> dict[str, Any] | None:
    wanted = normalize_sku(sku)

    for product in products:
        if normalize_sku(product.get("sku")) == wanted:
            return product

    return None

def product_matches_brand(
    product: dict[str, Any],
    brand: str | None,
) -> bool:
    if not brand:
        return True

    wanted = brand.strip().casefold()

    if not wanted:
        return True

    searchable_values: list[str] = [
        str(product.get("name") or ""),
        str(product.get("brand") or ""),
        str(product.get("producer") or ""),
    ]

    for key in ("categories", "tags", "attributes"):
        values = product.get(key, [])

        if not isinstance(values, list):
            continue

        for item in values:
            if not isinstance(item, dict):
                continue

            searchable_values.extend(
                [
                    str(item.get("name") or ""),
                    str(item.get("option") or ""),
                    str(item.get("slug") or ""),
                ]
            )

            options = item.get("options", [])

            if isinstance(options, list):
                searchable_values.extend(
                    str(option)
                    for option in options
                )

    searchable_text = " ".join(searchable_values).casefold()
    return wanted in searchable_text

def sync_one_product(
    sku: str,
    *,
    apply: bool = False,
    use_cache: bool = False,
    verbose: bool = True,
) -> bool:
    normalized_sku = normalize_sku(sku)
    product = get_product_by_sku(normalized_sku)

    if not product:
        print(
            f"SKU {normalized_sku} WooCommerce netika atrasts."
        )
        return False

    print(
        f"\n{normalized_sku} | "
        f"{product.get('name', '')}"
    )

    with create_brandfolder_session() as session:
        result = process_product(
            product,
            session=session,
            apply=apply,
            use_cache=use_cache,
            verbose=verbose,
        )

    return (
        result["action"] == "UPDATED"
        and result["verify_status"] == "OK"
    )

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Auditē un droši sinhronizē Brandfolder "
            "attēlus uz WooCommerce."
        )
    )

    parser.add_argument(
        "sku",
        nargs="?",
        help="Viena WooCommerce produkta SKU.",
    )

    parser.add_argument(
        "--brand",
        help="Apstrādāt tikai norādītā zīmola produktus.",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Apstrādāt visus WooCommerce produktus.",
    )

    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Izlaist sākumā norādīto produktu skaitu.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        help="Maksimālais apstrādājamo produktu skaits.",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Reāli augšupielādēt attēlus.",
    )

    parser.add_argument(
        "--cache",
        action="store_true",
        help="Izmantot Brandfolder kešatmiņu.",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Parādīt detalizētus attēlu sarakstus.",
    )

    return parser.parse_args()

def main() -> int:
    args = parse_args()

    if args.offset < 0:
        print("Kļūda: --offset nevar būt negatīvs.")
        return 2

    if args.limit is not None and args.limit < 1:
        print("Kļūda: --limit jābūt vismaz 1.")
        return 2

    selection_modes = sum(
        [
            bool(args.sku),
            bool(args.brand),
            bool(args.all),
        ]
    )

    if selection_modes == 0:
        print(
            "Kļūda: norādi SKU, --brand vai --all."
        )
        return 2

    if selection_modes > 1:
        print(
            "Kļūda: vienlaikus izmanto tikai vienu no "
            "SKU, --brand vai --all."
        )
        return 2

    if args.sku:
        product = get_product_by_sku(
            normalize_sku(args.sku),
        )

        if not product:
            print(
                f"SKU {normalize_sku(args.sku)} "
                "WooCommerce netika atrasts."
            )
            return 1

        selected_products = [product]

    else:
        products = load_products()

        filtered_products = [
            product
            for product in products
            if product_matches_brand(
                product,
                args.brand,
            )
        ]

        start = args.offset
        end = (
            None
            if args.limit is None
            else start + args.limit
        )

        selected_products = filtered_products[start:end]

        if args.brand:
            print(
                f'Pēc zīmola filtra "{args.brand}" '
                f"atrasti {len(filtered_products)} produkti."
            )

    print(
        f"Apstrādās {len(selected_products)} produktus."
    )

    if args.apply:
        print(
            "REĀLAIS REŽĪMS — SYNC produkti tiks mainīti."
        )
    else:
        print(
            "DRY RUN — WooCommerce nekas netiks mainīts."
        )

    results: list[dict[str, Any]] = []

    with create_brandfolder_session() as session:
        for index, product in enumerate(
            selected_products,
            start=1,
        ):
            sku = normalize_sku(product.get("sku"))
            name = str(product.get("name") or "").strip()

            print("\n" + "=" * 70)
            print(
                f"[{index}/{len(selected_products)}] "
                f"{sku or '(nav SKU)'} | {name}"
            )

            result = process_product(
                product,
                session=session,
                apply=args.apply,
                use_cache=args.cache,
                verbose=args.verbose,
            )
            results.append(result)

    print_sync_summary(results)

    try:
        if args.sku:
            selection = f"SKU: {normalize_sku(args.sku)}"
        elif args.brand:
            selection = f"Zīmols: {args.brand}"
        else:
            selection = "Visi produkti"

        report_path = generate_html_report(
            results=results,
            brand=args.brand,
            apply=args.apply,
            selection=selection,
        )
        print(f"HTML atskaite:    {report_path}")
    except Exception as exc:
        print(f"HTML atskaiti neizdevās izveidot: {exc}")

    return sync_exit_code(results)

if __name__ == "__main__":
    raise SystemExit(main())
