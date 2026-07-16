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


def normalize_sku(value: Any) -> str:
    """
    Normalizē WooCommerce SKU.

    Brandfolder specifiskā sufiksu apstrāde notiek
    src/brandfolder.py modulī.
    """
    return str(value or "").strip().upper()


def format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    return f"{minutes:02d}:{seconds:02d}"


def get_display_filename(image: dict[str, Any]) -> str:
    return str(
        image.get("filename")
        or image.get("name")
        or image.get("src")
        or ""
    )


def select_products(
    products: list[dict[str, Any]],
    limit: int | None,
) -> list[dict[str, Any]]:
    """
    Atlasa produktus ar aizpildītu SKU.

    --limit attiecas uz produktiem ar SKU, nevis uz
    tukšiem vai nederīgiem WooCommerce ierakstiem.
    """
    products_with_sku = [
        product
        for product in products
        if normalize_sku(product.get("sku"))
    ]

    if limit is None:
        return products_with_sku

    return products_with_sku[:limit]


def print_product_plan(
    *,
    number: int,
    total: int,
    sku: str,
    product: dict[str, Any],
    existing_count: int,
    brandfolder_count: int,
    already_present_count: int,
    missing_images: list[dict[str, Any]],
    verbose: bool,
) -> None:
    print("\n" + "-" * 72)
    print(
        f"[{number}/{total}] "
        f"SKU {sku} | {product.get('name', '')}"
    )
    print("-" * 72)

    print(f"WooCommerce attēli:       {existing_count}")
    print(f"Brandfolder unikālie:     {brandfolder_count}")
    print(f"Jau ir WooCommerce:       {already_present_count}")
    print(f"Trūkstošie:               {len(missing_images)}")

    if verbose and missing_images:
        print("\nPievienojamie attēli:")

        for image in missing_images:
            print(f"  + {get_display_filename(image)}")


def sync_images(
    *,
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
    print(
        "Režīms:  "
        + (
            "REĀLA SINHRONIZĀCIJA"
            if apply
            else "DRY RUN — izmaiņas netiks veiktas"
        )
    )

    if limit is not None:
        print(f"Limits:  pirmie {limit} produkti ar SKU")
    else:
        print("Limits:  visi WooCommerce produkti ar SKU")

    print("\nNolasa WooCommerce produktus...")

    try:
        all_products = load_products()
    except Exception as error:
        print(f"\n❌ Neizdevās nolasīt WooCommerce produktus: {error}")
        return 1

    products = select_products(
        products=all_products,
        limit=limit,
    )

    print(f"\nProdukti apstrādei: {len(products)}")

    if not products:
        print("Nav produktu, ko apstrādāt.")
        return 0

    statistics: Counter[str] = Counter()

    # Detalizēti kļūdu ieraksti gala kopsavilkumam.
    errors: list[dict[str, str]] = []

    with create_brandfolder_session() as brandfolder_session:
        for number, product in enumerate(products, start=1):
            sku = normalize_sku(product.get("sku"))
            product_id = product.get("id")
            product_name = str(product.get("name") or "")

            if not sku:
                statistics["without_sku"] += 1
                continue

            try:
                brandfolder_images = get_product_images(
                    sku,
                    use_cache=use_cache,
                    session=brandfolder_session,
                )

                if not brandfolder_images:
                    print(
                        f"\n[{number}/{len(products)}] "
                        f"SKU {sku} | {product_name}"
                    )
                    print("⚪ Brandfolder produkta attēli nav atrasti.")

                    statistics["no_brandfolder"] += 1
                    continue

                plan = prepare_image_update(
                    product=product,
                    raw_brandfolder_images=brandfolder_images,
                )

                existing_images = plan.get(
                    "existing_images",
                    [],
                )
                unique_brandfolder_images = plan.get(
                    "brandfolder_images",
                    [],
                )
                already_present = plan.get(
                    "already_present",
                    [],
                )
                missing_images = plan.get(
                    "missing_images",
                    [],
                )
                payload_images = plan.get(
                    "payload_images",
                    [],
                )

                print_product_plan(
                    number=number,
                    total=len(products),
                    sku=sku,
                    product=product,
                    existing_count=len(existing_images),
                    brandfolder_count=len(
                        unique_brandfolder_images
                    ),
                    already_present_count=len(
                        already_present
                    ),
                    missing_images=missing_images,
                    verbose=verbose,
                )

                if not missing_images:
                    print("✅ Produkta attēli jau ir aktuāli.")
                    statistics["unchanged"] += 1
                    continue

                if not apply:
                    print(
                        f"🔎 DRY RUN — tiktu pievienoti "
                        f"{len(missing_images)} attēli."
                    )
                    statistics["planned"] += 1
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

                print(
                    "✅ Atjaunināts. "
                    "WooCommerce attēlu skaits: "
                    f"{len(updated_images)}"
                )

                statistics["updated"] += 1
                statistics["added_images"] += len(
                    missing_images
                )

            except KeyboardInterrupt:
                print("\n\nDarbība pārtraukta ar tastatūru.")
                return 130

            except (
                BrandfolderError,
                ImageSyncError,
                requests.RequestException,
                ValueError,
                TypeError,
                KeyError,
            ) as error:
                print(
                    f"\n❌ SKU {sku}: {error}"
                )

                statistics["errors"] += 1

                errors.append(
                    {
                        "sku": sku,
                        "product": product_name,
                        "error": str(error),
                    }
                )

                # Turpinām ar nākamo produktu.
                continue

            except Exception as error:
                print(
                    f"\n❌ SKU {sku}: "
                    f"negaidīta kļūda: {error}"
                )

                statistics["errors"] += 1

                errors.append(
                    {
                        "sku": sku,
                        "product": product_name,
                        "error": (
                            f"{type(error).__name__}: {error}"
                        ),
                    }
                )

                continue

    elapsed = time.monotonic() - started_at

    print("\n" + "=" * 72)
    print("ATTĒLU SINHRONIZĀCIJAS KOPSAVILKUMS")
    print("=" * 72)

    print(f"Apstrādei atlasīti:       {len(products)}")
    print(f"Jau aktuāli:              {statistics['unchanged']}")
    print(
        f"Bez Brandfolder attēliem: {statistics['no_brandfolder']}"
    )

    if apply:
        print(f"Atjaunināti produkti:     {statistics['updated']}")
        print(
            f"Pievienoti attēli:        "
            f"{statistics['added_images']}"
        )
    else:
        print(
            f"Plānoti atjauninājumi:    "
            f"{statistics['planned']}"
        )
        print(
            f"Plānots pievienot attēlus:"
            f" {statistics['planned_images']}"
        )

    print(f"Kļūdas:                   {statistics['errors']}")
    print(f"Izpildes laiks:           {format_duration(elapsed)}")

    if errors:
        print("\nKļūdu saraksts:")

        for error in errors:
            print(
                f"  - SKU {error['sku']} | "
                f"{error['product']}: "
                f"{error['error']}"
            )

    print("=" * 72)

    if not apply:
        print(
            "\nDRY RUN pabeigts — WooCommerce nekas netika mainīts."
        )

        print(
            "\nReālai palaišanai izmanto:"
        )

        command = "python3 sync.py --images --apply"

        if limit is not None:
            command += f" --limit {limit}"

        if use_cache:
            command += " --cache"

        if verbose:
            command += " --verbose"

        print(command)

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
        "--limit",
        type=int,
        default=None,
        help=(
            "Apstrādāt tikai pirmos N WooCommerce "
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
            "kešatmiņu, ja tā ir pieejama."
        ),
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help=(
            "Parādīt visu pievienojamo attēlu failu "
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


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    validate_arguments(
        parser,
        args,
    )

    if args.images:
        return sync_images(
            limit=args.limit,
            apply=args.apply,
            use_cache=args.cache,
            verbose=args.verbose,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())