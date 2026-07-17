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


VERSION = "0.3.1"


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


def filter_products(
    products: list[dict[str, Any]],
    *,
    brand: str | None,
) -> list[dict[str, Any]]:
    """
    Atlasa produktus:
      - ar aizpildītu SKU;
      - pēc zīmola, ja --brand ir norādīts.
    """
    selected: list[dict[str, Any]] = []

    for product in products:
        sku = normalize_sku(product.get("sku"))

        if not sku:
            continue

        if brand and not product_has_brand(product, brand):
            continue

        selected.append(product)

    return selected


def select_product_range(
    products: list[dict[str, Any]],
    *,
    offset: int,
    limit: int | None,
) -> list[dict[str, Any]]:
    """
    Piemēri:

      offset=0, limit=20
      → pirmie 20 produkti

      offset=20, limit=30
      → izlaiž pirmos 20 un paņem nākamos 30

      offset=50, limit=None
      → visi produkti, sākot no 51.
    """
    if limit is None:
        return products[offset:]

    return products[offset:offset + limit]


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
    catalogue_position: int,
    product: dict[str, Any],
) -> None:
    sku = normalize_sku(product.get("sku"))
    name = str(product.get("name") or "")

    print("\n" + "-" * 72)
    print(
        f"[{number}/{total}] "
        f"Kataloga pozīcija {catalogue_position} | "
        f"SKU {sku} | {name}"
    )
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
    offset: int,
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
    print(f"Offset:  {offset}")

    if limit is None:
        print("Limits:  visi produkti pēc offset")
    else:
        print(f"Limits:  {limit} produkti pēc offset")

    print("\nNolasa WooCommerce produktus...")

    try:
        all_products = load_products()
    except Exception as error:
        print(
            "\n❌ Neizdevās nolasīt WooCommerce produktus: "
            f"{error}"
        )
        return 1

    filtered_products = filter_products(
        all_products,
        brand=brand,
    )

    products = select_product_range(
        filtered_products,
        offset=offset,
        limit=limit,
    )

    print(f"\nWooCommerce produkti kopā: {len(all_products)}")
    print(f"Atlasīti pēc zīmola/SKU:   {len(filtered_products)}")
    print(f"Izlaisti ar --offset:      {min(offset, len(filtered_products))}")
    print(f"Produkti apstrādei:        {len(products)}")

    if not products:
        print(
            "\nNav atrasts neviens produkts norādītajā diapazonā."
        )

        if offset >= len(filtered_products):
            print(
                f"Offset {offset} ir lielāks vai vienāds ar "
                f"atlasīto produktu skaitu {len(filtered_products)}."
            )

        return 0

    statistics: Counter[str] = Counter()
    errors: list[dict[str, str]] = []

    with create_brandfolder_session() as brandfolder_session:
        for number, product in enumerate(products, start=1):
            sku = normalize_sku(product.get("sku"))
            product_id = product.get("id")
            product_name = str(product.get("name") or "")

            catalogue_position = offset + number

            print_product_header(
                number=number,
                total=len(products),
                catalogue_position=catalogue_position,
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
                    f"⬆️ Apstrādā un pievieno "
                    f"{len(missing_images)} trūkstošos attēlus..."
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
                print("\n\nDarbība pārtraukta ar Ctrl+C.")
                print(
                    "Pēdējā apstrādātā kataloga pozīcija: "
                    f"{catalogue_position}"
                )
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
                        "position": str(catalogue_position),
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
                        "position": str(catalogue_position),
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

    print(f"Zīmols:                    {brand or 'visi zīmoli'}")
    print(f"Offset:                    {offset}")
    print(
        "Diapazons:                 "
        f"{offset + 1}–{offset + len(products)}"
    )
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
                f"  - Pozīcija {item['position']} | "
                f"SKU {item['sku']} | "
                f"{item['product']}: "
                f"{item['error']}"
            )

    print("=" * 72)

    next_offset = offset + len(products)

    if next_offset < len(filtered_products):
        print(
            "\nNākamā diapazona sākuma offset: "
            f"{next_offset}"
        )

        next_command_parts = [
            "python3",
            "sync.py",
            "--images",
        ]

        if brand:
            next_command_parts.extend(
                [
                    "--brand",
                    f'"{brand}"',
                ]
            )

        next_command_parts.extend(
            [
                "--offset",
                str(next_offset),
            ]
        )

        if limit is not None:
            next_command_parts.extend(
                [
                    "--limit",
                    str(limit),
                ]
            )

        if apply:
            next_command_parts.append("--apply")

        if use_cache:
            next_command_parts.append("--cache")

        if verbose:
            next_command_parts.append("--verbose")

        print("\nNākamajai produktu grupai:")
        print(" ".join(next_command_parts))
    else:
        print(
            "\n✅ Sasniegtas atlasītā produktu saraksta beigas."
        )

    if not apply:
        print(
            "\nDRY RUN pabeigts — WooCommerce nekas "
            "netika mainīts."
        )

        apply_command_parts = [
            "python3",
            "sync.py",
            "--images",
        ]

        if brand:
            apply_command_parts.extend(
                [
                    "--brand",
                    f'"{brand}"',
                ]
            )

        apply_command_parts.extend(
            [
                "--offset",
                str(offset),
            ]
        )

        if limit is not None:
            apply_command_parts.extend(
                [
                    "--limit",
                    str(limit),
                ]
            )

        apply_command_parts.append("--apply")

        if use_cache:
            apply_command_parts.append("--cache")

        if verbose:
            apply_command_parts.append("--verbose")

        print("\nŠī paša diapazona reālai palaišanai:")
        print(" ".join(apply_command_parts))

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
        "--offset",
        type=int,
        default=0,
        help=(
            "Izlaist pirmos N atlasītos produktus. "
            "Piemēram, --offset 20 sāk ar 21. produktu."
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Apstrādāt tikai N produktus pēc offset."
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

    if args.offset < 0:
        parser.error(
            "--offset nedrīkst būt negatīvs."
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
            offset=args.offset,
            limit=args.limit,
            apply=args.apply,
            use_cache=args.cache,
            verbose=args.verbose,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())