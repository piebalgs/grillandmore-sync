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
    get_product_images,
)
from src.image_sync import (
    ImageSyncError,
    prepare_image_update,
    update_product_images,
)
from src.woocommerce import load_products


VERSION = "0.2.0"


def normalize_text(value: Any) -> str:
    return str(value or "").strip().casefold()


def normalize_sku(value: Any) -> str:
    return str(value or "").strip().upper()


def format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    return f"{minutes:02d}:{seconds:02d}"


def product_has_brand(
    product: dict[str, Any],
    requested_brand: str,
) -> bool:
    """
    Pārbauda WooCommerce produkta brands lauku.

    Piemērs:
      "brands": [
          {
              "id": 241,
              "name": "Weber",
              "slug": "weber",
          }
      ]
    """
    wanted = normalize_text(requested_brand)

    if not wanted:
        return True

    brands = product.get("brands", [])

    if not isinstance(brands, list):
        return False

    for brand in brands:
        if not isinstance(brand, dict):
            continue

        brand_name = normalize_text(brand.get("name"))
        brand_slug = normalize_text(brand.get("slug"))

        if wanted in {brand_name, brand_slug}:
            return True

    return False


def select_products(
    products: list[dict[str, Any]],
    *,
    brand: str | None,
    limit: int | None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []

    for product in products:
        sku = normalize_sku(product.get("sku"))

        if not sku:
            continue

        if brand and not product_has_brand(product, brand):
            continue

        selected.append(product)

    if limit is not None:
        return selected[:limit]

    return selected


def display_filename(image: dict[str, Any]) -> str:
    return str(
        image.get("filename")
        or image.get("name")
        or image.get("src")
        or image.get("url")
        or ""
    )


def print_product_header(
    *,
    number: int,
    total: int,
    product: dict[str, Any],
) -> None:
    sku = normalize_sku(product.get("sku"))
    name = str(product.get("name") or "")

    print("\n" + "-" * 72)
    print(f"[{number}/{total}] SKU {sku} | {name}")
    print("-" * 72)


def print_plan(
    plan: dict[str, Any],
    *,
    verbose: bool,
) -> None:
    existing_images = plan.get("existing_images", [])
    brandfolder_images = plan.get("brandfolder_images", [])
    already_present = plan.get("already_present", [])
    missing_images = plan.get("missing_images", [])

    print(f"WooCommerce attēli:       {len(existing_images)}")
    print(f"Brandfolder unikālie:     {len(brandfolder_images)}")
    print(f"Jau ir WooCommerce:       {len(already_present)}")
    print(f"Trūkstošie:               {len(missing_images)}")

    if verbose and missing_images:
        print("\nPievienojamie attēli:")

        for image in missing_images:
            print(f"  + {display_filename(image)}")


def sync_images(
    *,
    brand: str | None,
    limit: int | None,
    apply: bool,
    use_cache: bool,
    verbose: bool,
) -> int:
    started_at = time.monotonic()

    print("=" * 72)
    print("GRILLANDMORE ATTĒLU SINHRONIZĀCIJA")
    print("=" * 72)
    print(f"Versija: {VERSION}")

    if apply:
        print("Režīms:  REĀLA SINHRONIZĀCIJA")
    else:
        print("Režīms:  DRY RUN — izmaiņas netiks veiktas")

    print(f"Zīmols:  {brand or 'visi zīmoli'}")

    if limit is None:
        print("Limits:  visi atlasītie produkti")
    else:
        print(f"Limits:  pirmie {limit} atlasītie produkti")

    print("\nNolasa WooCommerce produktus...")

    try:
        all_products = load_products()
    except Exception as error:
        print(
            "\n❌ Neizdevās nolasīt WooCommerce produktus: "
            f"{error}"
        )
        return 1

    products = select_products(
        all_products,
        brand=brand,
        limit=limit,
    )

    print(f"\nWooCommerce produkti kopā: {len(all_products)}")
    print(f"Produkti apstrādei:         {len(products)}")

    if not products:
        print(
            "\nNav atrasts neviens produkts, kas atbilst "
            "norādītajiem filtriem."
        )
        return 0

    statistics: Counter[str] = Counter()
    errors: list[dict[str, str]] = []

    with create_brandfolder_session() as brandfolder_session:
        for number, product in enumerate(products, start=1):
            sku = normalize_sku(product.get("sku"))
            product_id = product.get("id")
            product_name = str(product.get("name") or "")

            print_product_header(
                number=number,
                total=len(products),
                product=product,
            )

            try:
                brandfolder_images = get_product_images(
                    sku,
                    use_cache=use_cache,
                    session=brandfolder_session,
                )

                if not brandfolder_images:
                    print("⚪ Brandfolder attēli nav atrasti.")
                    statistics["no_brandfolder"] += 1
                    continue

                plan = prepare_image_update(
                    product=product,
                    raw_brandfolder_images=brandfolder_images,
                )

                print_plan(
                    plan,
                    verbose=verbose,
                )

                missing_images = plan.get(
                    "missing_images",
                    [],
                )

                payload_images = plan.get(
                    "payload_images",
                    [],
                )

                if not missing_images:
                    print("✅ Produkta attēli jau ir aktuāli.")
                    statistics["unchanged"] += 1
                    continue

                if not apply:
                    print(
                        "🔎 DRY RUN — tiktu pievienoti "
                        f"{len(missing_images)} attēli."
                    )

                    statistics["planned_products"] += 1
                    statistics["planned_images"] += len(
                        missing_images
                    )
                    continue

                if not product_id:
                    raise ImageSyncError(
                        "WooCommerce produktam nav ID."
                    )

                print(
                    f"⬆️ Pievieno {len(missing_images)} "
                    "trūkstošos attēlus..."
                )

                updated_product = update_product_images(
                    product_id=int(product_id),
                    payload_images=payload_images,
                )

                updated_images = updated_product.get(
                    "images",
                    [],
                )

                updated_count = (
                    len(updated_images)
                    if isinstance(updated_images, list)
                    else 0
                )

                print(
                    "✅ Produkts atjaunināts. "
                    "WooCommerce attēlu skaits: "
                    f"{updated_count}"
                )

                statistics["updated_products"] += 1
                statistics["added_images"] += len(
                    missing_images
                )

            except KeyboardInterrupt:
                print("\n\nDarbība pārtraukta.")
                return 130

            except (
                BrandfolderError,
                ImageSyncError,
                requests.RequestException,
                ValueError,
                TypeError,
                KeyError,
            ) as error:
                print(f"❌ Kļūda: {error}")

                statistics["errors"] += 1

                errors.append(
                    {
                        "sku": sku,
                        "product": product_name,
                        "error": str(error),
                    }
                )

                continue

            except Exception as error:
                error_message = (
                    f"{type(error).__name__}: {error}"
                )

                print(
                    "❌ Negaidīta kļūda: "
                    f"{error_message}"
                )

                statistics["errors"] += 1

                errors.append(
                    {
                        "sku": sku,
                        "product": product_name,
                        "error": error_message,
                    }
                )

                continue

    elapsed = time.monotonic() - started_at

    print("\n" + "=" * 72)
    print("ATTĒLU SINHRONIZĀCIJAS KOPSAVILKUMS")
    print("=" * 72)

    print(f"Atlasīti produkti:         {len(products)}")
    print(f"Jau aktuāli:               {statistics['unchanged']}")
    print(
        "Bez Brandfolder attēliem: "
        f"{statistics['no_brandfolder']}"
    )

    if apply:
        print(
            "Atjaunināti produkti:      "
            f"{statistics['updated_products']}"
        )
        print(
            "Pievienoti attēli:         "
            f"{statistics['added_images']}"
        )
    else:
        print(
            "Plānoti produkti:          "
            f"{statistics['planned_products']}"
        )
        print(
            "Plānots pievienot attēlus: "
            f"{statistics['planned_images']}"
        )

    print(f"Kļūdas:                    {statistics['errors']}")
    print(f"Izpildes laiks:            {format_duration(elapsed)}")

    if errors:
        print("\nKļūdu saraksts:")

        for item in errors:
            print(
                f"  - SKU {item['sku']} | "
                f"{item['product']}: "
                f"{item['error']}"
            )

    print("=" * 72)

    if not apply:
        print(
            "\nDRY RUN pabeigts — WooCommerce nekas "
            "netika mainīts."
        )

        command_parts = [
            "python3",
            "sync.py",
            "--images",
        ]

        if brand:
            command_parts.extend(
                [
                    "--brand",
                    f'"{brand}"',
                ]
            )

        if limit is not None:
            command_parts.extend(
                [
                    "--limit",
                    str(limit),
                ]
            )

        command_parts.append("--apply")

        if use_cache:
            command_parts.append("--cache")

        if verbose:
            command_parts.append("--verbose")

        print("\nReālai palaišanai:")
        print(" ".join(command_parts))

    return 1 if statistics["errors"] else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "GrillAndMore WooCommerce produktu "
            "sinhronizācijas rīks."
        )
    )

    parser.add_argument(
        "--images",
        action="store_true",
        help=(
            "Sinhronizēt WooCommerce produktu attēlus "
            "no Brandfolder."
        ),
    )

    parser.add_argument(
        "--brand",
        type=str,
        default=None,
        help=(
            "Apstrādāt tikai norādītā WooCommerce "
            "zīmola produktus, piemēram, Weber."
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Apstrādāt tikai pirmos N atlasītos "
            "produktus ar SKU."
        ),
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Reāli veikt izmaiņas WooCommerce. "
            "Bez šī parametra darbojas DRY RUN."
        ),
    )

    parser.add_argument(
        "--cache",
        action="store_true",
        help=(
            "Izmantot iepriekš saglabāto Brandfolder "
            "kešatmiņu."
        ),
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help=(
            "Parādīt pievienojamo attēlu failu "
            "nosaukumus."
        ),
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )

    return parser


def validate_arguments(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    if not args.images:
        parser.error(
            "Pašlaik jānorāda darbība --images."
        )

    if args.limit is not None and args.limit <= 0:
        parser.error(
            "--limit jābūt pozitīvam veselam skaitlim."
        )

    if args.brand is not None and not args.brand.strip():
        parser.error(
            "--brand vērtība nedrīkst būt tukša."
        )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    validate_arguments(
        parser,
        args,
    )

    if args.images:
        return sync_images(
            brand=args.brand,
            limit=args.limit,
            apply=args.apply,
            use_cache=args.cache,
            verbose=args.verbose,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())