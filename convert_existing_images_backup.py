#!/usr/bin/env python3

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import requests

from src.image_processor import (
    ImageProcessingError,
    describe_processed_image,
    process_remote_image,
)
from src.image_sync import (
    ImageSyncError,
    put_product_image_ids,
    upload_media_file,
    validate_configuration,
)
from src.woocommerce import load_products


CONVERTIBLE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
WEBP_EXTENSION = ".webp"
PRODUCT_PAUSE_SECONDS = 3


def filename_from_url(url: Any) -> str:
    text = str(url or "").strip()

    if not text:
        return ""

    parsed = urlparse(text)
    return Path(unquote(parsed.path)).name


def image_extension(image: dict[str, Any]) -> str:
    filename = filename_from_url(image.get("src"))

    if not filename:
        filename = str(image.get("name") or "").strip()

    return Path(filename).suffix.lower()


def image_filename(image: dict[str, Any]) -> str:
    return (
        filename_from_url(image.get("src"))
        or str(image.get("name") or "").strip()
        or "product-image"
    )


def product_has_brand(
    product: dict[str, Any],
    wanted_brand: str,
) -> bool:
    wanted = wanted_brand.strip().casefold()

    if not wanted:
        return True

    brands = product.get("brands", [])

    if isinstance(brands, list):
        for brand in brands:
            if not isinstance(brand, dict):
                continue

            name = str(
                brand.get("name")
                or brand.get("slug")
                or ""
            ).strip()

            if name.casefold() == wanted:
                return True

    attributes = product.get("attributes", [])

    if isinstance(attributes, list):
        for attribute in attributes:
            if not isinstance(attribute, dict):
                continue

            attribute_name = str(
                attribute.get("name")
                or ""
            ).strip().casefold()

            if attribute_name not in {
                "brand",
                "brands",
                "zīmols",
                "zimols",
            }:
                continue

            options = attribute.get("options", [])

            if isinstance(options, list):
                for option in options:
                    if str(option).strip().casefold() == wanted:
                        return True

    return False


def get_product_images(
    product: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_images = product.get("images", [])

    if not isinstance(raw_images, list):
        return []

    return [
        image
        for image in raw_images
        if isinstance(image, dict)
    ]


def classify_images(
    images: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    webp: list[dict[str, Any]] = []
    convertible: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []

    for image in images:
        extension = image_extension(image)

        if extension == WEBP_EXTENSION:
            webp.append(image)
        elif extension in CONVERTIBLE_EXTENSIONS:
            convertible.append(image)
        else:
            unsupported.append(image)

    return webp, convertible, unsupported


def selected_products(
    *,
    brand: str,
    offset: int,
    limit: int | None,
) -> tuple[list[dict[str, Any]], int]:
    products = load_products()

    matching = [
        product
        for product in products
        if isinstance(product, dict)
        and product_has_brand(product, brand)
    ]

    matching.sort(
        key=lambda product: (
            str(product.get("name") or "").casefold(),
            int(product.get("id") or 0),
        )
    )

    total = len(matching)

    if limit is None:
        return matching[offset:], total

    return matching[offset:offset + limit], total


def migrate_product(
    product: dict[str, Any],
    *,
    download_session: requests.Session,
) -> tuple[int, int]:
    product_id = product.get("id")

    if not product_id:
        raise ImageSyncError(
            "WooCommerce produktam nav ID."
        )

    images = get_product_images(product)
    replacement_ids: list[int] = []

    converted_count = 0
    retained_count = 0
    newly_uploaded_ids: list[int] = []

    try:
        for position, image in enumerate(images, start=1):
            image_id = image.get("id")
            source_url = str(
                image.get("src")
                or ""
            ).strip()

            extension = image_extension(image)
            original_filename = image_filename(image)

            if extension == WEBP_EXTENSION:
                if image_id:
                    replacement_ids.append(int(image_id))
                    retained_count += 1
                continue

            if extension not in CONVERTIBLE_EXTENSIONS:
                if image_id:
                    replacement_ids.append(int(image_id))
                    retained_count += 1

                print(
                    f"    ⚠ {position}. {original_filename}: "
                    "formāts netiek pārveidots; esošais attēls saglabāts."
                )
                continue

            if not source_url:
                raise ImageSyncError(
                    f"Attēlam {original_filename} nav URL."
                )

            alt_text = str(
                image.get("alt")
                or image.get("name")
                or Path(original_filename).stem
            ).strip()

            print(
                f"    [{position}/{len(images)}] "
                f"{original_filename}"
            )

            processed = process_remote_image(
                url=source_url,
                filename=original_filename,
                session=download_session,
                use_cache=True,
            )

            if (
                processed.content_type != "image/webp"
                or processed.path.suffix.lower() != ".webp"
            ):
                raise ImageProcessingError(
                    "image_processor.py neatgrieza WebP failu. "
                    "Pārbaudi, vai projektā ir ievietota jaunā WebP versija."
                )

            print(
                "      "
                + describe_processed_image(processed)
            )

            media = upload_media_file(
                file_path=processed.path,
                filename=processed.filename,
                content_type=processed.content_type,
                alt_text=alt_text,
            )

            new_media_id = int(media["id"])

            newly_uploaded_ids.append(new_media_id)
            replacement_ids.append(new_media_id)
            converted_count += 1

            print(
                f"      ✓ Jaunais Media Library ID: "
                f"{new_media_id}"
            )

        if len(replacement_ids) != len(images):
            raise ImageSyncError(
                "Jauno attēlu saraksta garums neatbilst "
                "sākotnējam galerijas garumam."
            )

        put_product_image_ids(
            product_id=int(product_id),
            image_ids=replacement_ids,
        )

        print(
            "    ✓ Produkta galerija atjaunināta; "
            "attēlu secība saglabāta."
        )

        return converted_count, retained_count

    except Exception:
        if newly_uploaded_ids:
            print(
                "    ⚠ Produkts netika mainīts, bet Media Library "
                "var būt palikuši šie jaunie, nepiesaistītie ID: "
                + ", ".join(str(value) for value in newly_uploaded_ids)
            )
        raise


def print_header(
    *,
    brand: str,
    offset: int,
    limit: int | None,
    apply: bool,
) -> None:
    print("\n" + "=" * 72)
    print("WOOCOMMERCE MEDIA LIBRARY → WEBP MIGRĀCIJA")
    print("=" * 72)
    print(f"Zīmols:          {brand}")
    print(f"Offset:          {offset}")
    print(
        "Limits:          "
        + (str(limit) if limit is not None else "visi")
    )
    print(
        "Režīms:          "
        + ("APPLY — reālas izmaiņas" if apply else "DRY RUN")
    )
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Pārveido esošos WooCommerce produktu PNG/JPG "
            "attēlus uz 800×800 WebP un saglabā galerijas secību."
        )
    )

    parser.add_argument(
        "--brand",
        required=True,
        help='WooCommerce zīmols, piemēram, "Weber".',
    )

    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Cik zīmola produktus izlaist no sākuma.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maksimālais apstrādājamo produktu skaits.",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Reāli augšupielādēt WebP un mainīt produktus.",
    )

    args = parser.parse_args()

    if args.offset < 0:
        parser.error("--offset nevar būt negatīvs.")

    if args.limit is not None and args.limit < 1:
        parser.error("--limit jābūt vismaz 1.")

    print_header(
        brand=args.brand,
        offset=args.offset,
        limit=args.limit,
        apply=args.apply,
    )

    started_at = time.monotonic()

    products, total_matching = selected_products(
        brand=args.brand,
        offset=args.offset,
        limit=args.limit,
    )

    products_with_conversion = 0
    already_webp_products = 0
    products_without_images = 0
    planned_images = 0
    unsupported_images = 0
    converted_images = 0
    retained_images = 0
    errors = 0

    download_session = requests.Session()
    download_session.headers.update(
        {
            "User-Agent": (
                "GrillAndMore-Sync/0.4 "
                "(Media Library WebP migration)"
            ),
            "Accept": "image/*,*/*;q=0.8",
        }
    )

    try:
        if args.apply:
            validate_configuration()

        for number, product in enumerate(products, start=1):
            name = str(product.get("name") or "")
            sku = str(product.get("sku") or "")
            product_id = product.get("id")
            images = get_product_images(product)

            print(
                f"\n[{number}/{len(products)}] "
                f"{sku} | {name} | ID {product_id}"
            )

            if not images:
                products_without_images += 1
                print("    — Produktam nav attēlu.")
                continue

            webp, convertible, unsupported = classify_images(images)

            unsupported_images += len(unsupported)

            print(
                f"    Attēli: {len(images)} | "
                f"WebP: {len(webp)} | "
                f"PNG/JPG: {len(convertible)} | "
                f"citi: {len(unsupported)}"
            )

            if not convertible:
                already_webp_products += 1
                print("    ✓ Nav PNG/JPG attēlu, ko pārveidot.")
                continue

            products_with_conversion += 1
            planned_images += len(convertible)

            if not args.apply:
                for image in convertible:
                    print(
                        "    PLĀNOTS: "
                        f"{image_filename(image)} → "
                        f"{Path(image_filename(image)).stem}.webp"
                    )
                continue

            try:
                converted, retained = migrate_product(
                    product,
                    download_session=download_session,
                )

                converted_images += converted
                retained_images += retained

                time.sleep(PRODUCT_PAUSE_SECONDS)

            except (
                ImageProcessingError,
                ImageSyncError,
                requests.RequestException,
                OSError,
                ValueError,
                TypeError,
            ) as error:
                errors += 1
                print(f"    ✗ KĻŪDA: {error}")

    finally:
        download_session.close()

    elapsed = int(time.monotonic() - started_at)
    minutes, seconds = divmod(elapsed, 60)

    print("\n" + "=" * 72)
    print("WEBP MIGRĀCIJAS KOPSAVILKUMS")
    print("=" * 72)
    print(f"Zīmols:                       {args.brand}")
    print(f"Zīmola produkti kopā:         {total_matching}")
    print(f"Atlasīti produkti:            {len(products)}")
    print(f"Produkti ar PNG/JPG:          {products_with_conversion}")
    print(f"Produkti jau bez PNG/JPG:     {already_webp_products}")
    print(f"Produkti bez attēliem:        {products_without_images}")
    print(f"Plānoti PNG/JPG attēli:       {planned_images}")
    print(f"Neatbalstīta formāta attēli:  {unsupported_images}")

    if args.apply:
        print(f"Pārveidoti WebP attēli:       {converted_images}")
        print(f"Saglabāti esošie attēli:      {retained_images}")

    print(f"Kļūdas:                       {errors}")
    print(f"Izpildes laiks:               {minutes:02d}:{seconds:02d}")
    print("=" * 72)

    next_offset = args.offset + len(products)

    print(
        f"\nNākamā diapazona sākuma offset: "
        f"{next_offset}"
    )

    if not args.apply:
        print(
            "\nDRY RUN pabeigts — WooCommerce nekas netika mainīts."
        )
        print("\nŠī paša diapazona reālai palaišanai:")
        command = (
            "python3 convert_existing_images.py "
            f'--brand "{args.brand}" '
            f"--offset {args.offset}"
        )

        if args.limit is not None:
            command += f" --limit {args.limit}"

        command += " --apply"
        print(command)
    else:
        print(
            "\nAPPLY pabeigts. Vecie PNG/JPG Media Library faili "
            "netika dzēsti."
        )


if __name__ == "__main__":
    main()
