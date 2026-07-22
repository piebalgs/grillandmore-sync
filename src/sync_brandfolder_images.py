#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from typing import Any

import requests

from src.brandfolder import (
    BrandfolderError,
    create_session as create_brandfolder_session,
)
from src.image_sync import ImageSyncError, process_product
from src.media_audit import normalize_sku, product_has_brand
from src.woocommerce import load_products

VERSION = "1.1.0"


def format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return (
        f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        if hours
        else f"{minutes:02d}:{seconds:02d}"
    )


def filter_products(
    products: list[dict[str, Any]],
    *,
    brand: str | None,
    exclude_brand: str | None,
    sku: str | None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    wanted_sku = normalize_sku(sku) if sku else ""

    for product in products:
        if not isinstance(product, dict):
            continue

        product_sku = normalize_sku(product.get("sku"))
        if not product_sku:
            continue
        if wanted_sku and product_sku != wanted_sku:
            continue
        if brand and not product_has_brand(product, brand):
            continue
        if exclude_brand and product_has_brand(product, exclude_brand):
            continue

        selected.append(product)

    return selected


def select_product_range(
    products: list[dict[str, Any]],
    *,
    offset: int,
    limit: int | None,
) -> list[dict[str, Any]]:
    if limit is None:
        return products[offset:]
    return products[offset:offset + limit]


def filter_text(args: argparse.Namespace) -> str:
    if args.sku:
        return f"SKU {normalize_sku(args.sku)}"
    if args.brand:
        return args.brand
    if args.exclude_brand:
        return f"visi, izņemot {args.exclude_brand}"
    return "visi zīmoli"


def print_header(args: argparse.Namespace) -> None:
    mode = "APPLY — WooCommerce tiks mainīts" if args.apply else "DRY RUN — izmaiņu nav"

    print("\n" + "=" * 72)
    print("BRANDFOLDER → WOOCOMMERCE ATTĒLU SINHRONIZĀCIJA")
    print("=" * 72)
    print(f"Versija:           {VERSION}")
    print(f"Filtrs:            {filter_text(args)}")
    print(f"Offset:            {args.offset}")
    print("Limits:            " + (str(args.limit) if args.limit is not None else "visi"))
    print("Brandfolder cache: " + ("JĀ" if args.cache else "NĒ"))
    print(f"Režīms:            {mode}")
    print("=" * 72)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Auditē un droši sinhronizē Brandfolder attēlus uz WooCommerce. "
            "Pēc noklusējuma darbojas DRY RUN režīmā."
        )
    )

    brand_group = parser.add_mutually_exclusive_group()
    brand_group.add_argument("--brand", default=None)
    brand_group.add_argument("--exclude-brand", default=None)

    parser.add_argument("--sku", default=None, help="Apstrādāt tikai vienu SKU.")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--cache", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Reāli augšupielādēt un piesaistīt attēlus WooCommerce.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return parser


def validate_arguments(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    if args.offset < 0:
        parser.error("--offset nedrīkst būt negatīvs.")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit jābūt pozitīvam veselam skaitlim.")
    if args.brand is not None and not args.brand.strip():
        parser.error("--brand vērtība nedrīkst būt tukša.")
    if args.exclude_brand is not None and not args.exclude_brand.strip():
        parser.error("--exclude-brand vērtība nedrīkst būt tukša.")
    if args.sku is not None and not normalize_sku(args.sku):
        parser.error("--sku vērtība nedrīkst būt tukša.")

    if args.apply and not (args.sku or args.brand or args.exclude_brand):
        parser.error(
            "--apply režīmā obligāti norādi --sku, --brand vai --exclude-brand."
        )


def run(args: argparse.Namespace) -> int:
    started_at = time.monotonic()
    print_header(args)

    try:
        all_products = load_products()
    except Exception as error:
        print(f"\n❌ Neizdevās nolasīt WooCommerce produktus: {error}")
        return 1

    filtered = filter_products(
        all_products,
        brand=args.brand,
        exclude_brand=args.exclude_brand,
        sku=args.sku,
    )
    filtered.sort(
        key=lambda product: (
            str(product.get("name") or "").casefold(),
            int(product.get("id") or 0),
        )
    )
    selected = select_product_range(
        filtered,
        offset=args.offset,
        limit=args.limit,
    )

    print(f"\nWooCommerce produkti kopā: {len(all_products)}")
    print(f"Atlasīti pēc filtra:       {len(filtered)}")
    print(f"Produkti apstrādei:         {len(selected)}\n")

    if not selected:
        print("Nav produktu apstrādei.")
        return 0

    statistics: Counter[str] = Counter()
    interrupted = False

    with create_brandfolder_session() as session:
        for number, product in enumerate(selected, start=1):
            sku = normalize_sku(product.get("sku"))
            catalogue_position = args.offset + number
            name = str(product.get("name") or "").strip()
            product_id = product.get("id")

            print(
                f"[{number}/{len(selected)}] katalogā #{catalogue_position} "
                f"| {sku} | ID {product_id}"
            )
            print(f"    {name}")

            try:
                result = process_product(
                    product,
                    session=session,
                    apply=args.apply,
                    use_cache=args.cache,
                    verbose=args.verbose,
                )

                action = str(result.get("action") or "ERROR")
                statistics[action] += 1

            except KeyboardInterrupt:
                interrupted = True
                print("\nPārtraukts ar Ctrl+C.")
                break
            except (
                BrandfolderError,
                ImageSyncError,
                requests.RequestException,
                ValueError,
                TypeError,
                KeyError,
            ) as error:
                statistics["ERROR"] += 1
                print(f"    ❌ ERROR — {error}")
            except Exception as error:
                statistics["ERROR"] += 1
                print(f"    ❌ ERROR — {type(error).__name__}: {error}")

            print()

    elapsed = time.monotonic() - started_at
    processed = sum(
        statistics[key]
        for key in (
            "SKIP_OK",
            "SKIP_REVIEW",
            "DRY_RUN",
            "UPDATED",
            "ERROR",
        )
    )

    print("=" * 72)
    print("BRANDFOLDER ATTĒLU SINHRONIZĀCIJAS KOPSAVILKUMS")
    print("=" * 72)
    print(f"Versija:                       {VERSION}")
    print(f"Režīms:                        {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"Filtrs:                        {filter_text(args)}")
    print(f"Atlasīti produkti:             {len(selected)}")
    print(f"Apstrādāti produkti:           {processed}")
    print(f"SKIP_OK — aktuāli:             {statistics['SKIP_OK']}")
    print(f"SKIP_REVIEW:                   {statistics['SKIP_REVIEW']}")
    print(f"DRY_RUN — plānoti:             {statistics['DRY_RUN']}")
    print(f"UPDATED:                       {statistics['UPDATED']}")
    print(f"ERROR:                         {statistics['ERROR']}")
    print(f"Izpildes laiks:                {format_duration(elapsed)}")
    print("=" * 72)

    next_offset = args.offset + processed
    print(f"\nNākamā diapazona offset: {next_offset}")

    if args.apply:
        print("\nAPPLY pabeigts.")
    else:
        print("\nDRY RUN pabeigts — WooCommerce nekas netika mainīts.")

    if interrupted:
        return 130
    return 1 if statistics["ERROR"] else 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    validate_arguments(parser, args)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
